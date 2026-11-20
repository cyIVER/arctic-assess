package notify

import (
	"context"
	"crypto/tls"
	"encoding/base64"
	"errors"
	"fmt"
	"mime"
	"net"
	"net/smtp"
	"strconv"
	"strings"
	"time"
)

// emailDialTimeout / emailSessionTimeout bound connection establishment and the entire SMTP session, respectively.
// net/smtp has no timeout mechanism. Without these two bounds, a stalled peer can leave
// the delivery goroutine blocked forever. Since the dispatcher processes serially in one goroutine,
// that would stop the entire notification system.
const (
	emailDialTimeout    = 10 * time.Second
	emailSessionTimeout = 45 * time.Second
)

// emailChannel implements SMTP email delivery.
type emailChannel struct{}

func (emailChannel) Kind() string { return KindEmail }

// Email has no platform rate limit, but should not spam recipients; use a generous default.
func (emailChannel) DefaultRatePerMin() int { return 60 }

// Mask only the password. SMTP host, account, and recipients are not secrets; masking them only complicates editing.
func (emailChannel) SecretKeys() []string { return []string{"password"} }

// host/port determine which server receives the password; tls determines transport encryption. Changing any of these
// requires explicitly resupplying the password, so disabling TLS also requires explicit credentials rather than an incidental edit.
func (emailChannel) DestinationKeys() []string { return []string{"host", "port", "tls"} }

func (emailChannel) Validate(cfg map[string]any) error {
	if cfgString(cfg, "host") == "" {
		return errors.New("Missing SMTP server address")
	}
	port := cfgInt(cfg, "port")
	if port <= 0 || port > 65535 {
		return errors.New("Invalid SMTP port (must be 1-65535)")
	}
	if cfgString(cfg, "from") == "" {
		return errors.New("Missing sender address")
	}
	if len(cfgStrings(cfg, "to")) == 0 {
		return errors.New("At least one recipient address is required")
	}
	return nil
}

func (c emailChannel) Send(ctx context.Context, cfg map[string]any, m Message) (int, error) {
	if err := c.Validate(cfg); err != nil {
		return 0, Permanent(err)
	}
	host := cfgString(cfg, "host")
	port := cfgInt(cfg, "port")
	from := cfgString(cfg, "from")
	to := cfgStrings(cfg, "to")
	username := cfgString(cfg, "username")
	password := cfgString(cfg, "password")
	implicitTLS := cfgBool(cfg, "tls")

	msg, err := buildEmailMessage(from, to, m)
	if err != nil {
		return 0, Permanent(err)
	}

	addr := net.JoinHostPort(host, strconv.Itoa(port))
	client, err := emailDial(ctx, addr, host, implicitTLS)
	if err != nil {
		return 0, err
	}
	defer client.Close()

	// STARTTLS: upgrade when supported. Never send credentials in a plaintext session (see auth below).
	if !implicitTLS {
		if ok, _ := client.Extension("STARTTLS"); ok {
			if err := client.StartTLS(&tls.Config{ServerName: host, MinVersion: tls.VersionTLS12}); err != nil {
				return 0, fmt.Errorf("STARTTLS failed: %w", err)
			}
		}
	}
	if username != "" {
		if err := client.Auth(smtp.PlainAuth("", username, password, host)); err != nil {
			// smtp.PlainAuth refuses to send credentials over an unencrypted connection unless the destination is localhost.
			// This is **correct** security behavior and must not be bypassed, but explain the cause clearly;
			// otherwise users see only "unencrypted connection" without knowing how to fix it.
			if strings.Contains(err.Error(), "unencrypted connection") {
				return 0, Permanent(fmt.Errorf("Refusing to send credentials over an unencrypted connection. Enable TLS, use port 465 (implicit TLS), or select Enable TLS (%w)", err))
			}
			return 0, Permanent(fmt.Errorf("SMTP authentication failed: %w", err))
		}
	}
	if err := client.Mail(from); err != nil {
		return 0, smtpStageError(fmt.Sprintf("Sender %s rejected", from), err)
	}
	for _, rcpt := range to {
		if err := client.Rcpt(rcpt); err != nil {
			return 0, smtpStageError(fmt.Sprintf("Recipient %s rejected", rcpt), err)
		}
	}
	w, err := client.Data()
	if err != nil {
		return 0, fmt.Errorf("SMTP DATA failed: %w", err)
	}
	if _, err := w.Write([]byte(msg)); err != nil {
		return 0, fmt.Errorf("Failed to write email body: %w", err)
	}
	if err := w.Close(); err != nil {
		return 0, fmt.Errorf("Failed to submit email: %w", err)
	}
	// A failed Quit does not change the fact that the server accepted the message; ignore that error.
	_ = client.Quit()
	// Email is not truncated (the entire HTML body is sent); count the whole batch as delivered.
	return len(m.Items), nil
}

// emailDial establishes an SMTP connection.
//
// implicitTLS=true uses immediate TLS, as on port 465; false connects in plaintext on 25/587 and then uses
// STARTTLS. Do not mix them: a plaintext greeting to port 465 causes an immediate disconnect.
//
// Set the session deadline **at connection establishment**, not afterward: net/smtp.Client hides the underlying
// connection in an unexported field. Once handed over, the previously set deadline is the only
// fallback. It also covers blocking during the handshake.
// Control attaches blockInternalDial, sharing the HTTP channels' guard. Without it SMTP
// would leave an SSRF gap: host values such as 169.254.169.254 or 127.0.0.1 could connect directly,
// and smtp.NewClient handshake failures include the peer's response line in errors, which last_error
// exposes through delivery history, creating a semi-blind read primitive. Timing differences between refusal and timeout
// could also probe ports. Dial-time enforcement is final and also covers DNS rebinding.
func emailDial(ctx context.Context, addr, host string, implicitTLS bool) (*smtp.Client, error) {
	d := &net.Dialer{Timeout: emailDialTimeout, Control: blockInternalDial}
	var conn net.Conn
	var err error
	if implicitTLS {
		conn, err = tls.DialWithDialer(d, "tcp", addr, &tls.Config{ServerName: host, MinVersion: tls.VersionTLS12})
	} else {
		conn, err = d.DialContext(ctx, "tcp", addr)
	}
	if err != nil {
		return nil, fmt.Errorf("Failed to connect to SMTP server: %w", err)
	}
	_ = conn.SetDeadline(time.Now().Add(emailSessionTimeout))
	client, err := smtp.NewClient(conn, host)
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("SMTP handshake failed: %w", err)
	}
	return client, nil
}

// smtpStageError classifies a stage failure as retryable or permanent using the SMTP reply code.
//
// The distinction matters because SMTP 4xx and 5xx have entirely different semantics:
//   - 4xx (450 greylisting, 451 local error, 452 insufficient storage) are **temporary** refusals;
//     retry later. Greylisting in particular occurs on nearly every first delivery attempt.
//   - 5xx (550 unknown user, 553 invalid address) are permanent refusals; retrying is pointless.
//
// Classifying all failures as permanent would move **every** notification to failed on its first
// attempt against a greylisting server, precisely where automatic retries are most useful.
// Read the first three digits of the error text as the reply code; if unavailable, treat it as retryable
// (prefer an extra retry over permanently rejecting a potentially transient failure because parsing failed).
func smtpStageError(what string, err error) error {
	code := smtpReplyCode(err.Error())
	if code >= 500 && code < 600 {
		return Permanent(fmt.Errorf("%s: %w", what, err))
	}
	return fmt.Errorf("%s: %w", what, err)
}

// smtpReplyCode extracts the leading three-digit reply code from SMTP error text, or returns 0 if absent.
// net/smtp exposes no error-code field, so parse text in the form "450 4.7.1 ...".
func smtpReplyCode(text string) int {
	if len(text) < 3 {
		return 0
	}
	n, err := strconv.Atoi(text[:3])
	if err != nil {
		return 0
	}
	return n
}

// buildEmailMessage assembles a complete RFC 5322 message.
//
// Base64-encode the body for two reasons: SMTP limits lines to 1000 bytes, while HTML
// bodies (especially batch emails) easily exceed that; base64 also never produces lines starting with ".",
// avoiding SMTP dot-stuffing concerns.
func buildEmailMessage(from string, to []string, m Message) (string, error) {
	var b strings.Builder
	fmt.Fprintf(&b, "From: %s\r\n", from)
	fmt.Fprintf(&b, "To: %s\r\n", strings.Join(to, ", "))
	// Chinese subjects require RFC 2047 encoding, or clients display garbled text.
	fmt.Fprintf(&b, "Subject: %s\r\n", mime.QEncoding.Encode("utf-8", htmlTitle(m)))
	b.WriteString("MIME-Version: 1.0\r\n")
	b.WriteString("Content-Type: text/html; charset=\"UTF-8\"\r\n")
	b.WriteString("Content-Transfer-Encoding: base64\r\n")
	// Email has no hard length limit, so do not truncate the body.
	b.WriteString("\r\n")
	encoded := base64.StdEncoding.EncodeToString([]byte(htmlBody(m, 0)))
	// Wrap base64 at 76 characters per line, per RFC 2045.
	for len(encoded) > 76 {
		b.WriteString(encoded[:76] + "\r\n")
		encoded = encoded[76:]
	}
	b.WriteString(encoded + "\r\n")
	return b.String(), nil
}
