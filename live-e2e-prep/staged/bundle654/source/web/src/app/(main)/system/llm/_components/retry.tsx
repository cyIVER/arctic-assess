"use client";

// Shared pieces for LLM retry settings: the "attempts + interval" of each of the five retry layers.
//
// The five layers, from innermost to outermost: connect (SDK) → empty response (SDK) → same-provider safe window → polling breaker → intent rerun.
// The first three follow the endpoint, so each model profile can override the global defaults; the last two are process-wide and only have a global copy.
//
// All inputs follow the same "empty = not configured" semantics, matching the backend db.RetryRule:
//   attempts  empty/0 = use built-in default | -1 = disable this retry layer | >0 = use this count
//   interval  empty/0 = use this layer's original exponential backoff | >0 = use this fixed millisecond interval

import * as React from "react";

import { Loader2Icon, SaveIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { LLMRetryOverride, LLMRetryPolicy, LLMRetryRule } from "@/lib/types";

export const ZERO_RULE: LLMRetryRule = { attempts: 0, interval_ms: 0 };
export const ZERO_OVERRIDE: LLMRetryOverride = {
  connect: ZERO_RULE,
  empty: ZERO_RULE,
  stream: ZERO_RULE,
};
const ZERO_POLICY: LLMRetryPolicy = {
  ...ZERO_OVERRIDE,
  breaker: ZERO_RULE,
  intent: ZERO_RULE,
};

type LayerMeta = {
  title: string;
  /** Where this retry layer lives and who runs it */
  where: string;
  /** What kind of errors reach this layer — down to the status codes, so nobody has to guess */
  trigger: string;
  /** Errors that look similar but do [not] go through this layer, so a no-op setting is not mistaken for a bug */
  skips?: string;
  desc: string;
  attemptsLabel: string;
  /** Default when attempts is empty, used for the placeholder */
  defAttempts: number;
  /** Default policy when interval is empty, used for the placeholder */
  defInterval: string;
  /** Meaning of entering -1 for attempts */
  offHint: string;
};

export const RETRY_LAYERS = {
  connect: {
    title: "Connect retry",
    where: "SDK · before a 200 is received",
    trigger:
      "Cannot connect or no 200 yet: network-layer errors such as connection reset / read-write timeout / DNS failure, plus HTTP 408, 429, 500, 502, 503, 504.",
    skips: "All other status codes (400 / 401 / 403 / 404 / 413 / 422, etc.) are deterministic rejections; resending fails the same way, so they are thrown immediately.",
    desc: "Resends the same request as-is. Once the stream starts (a 200 has been received), a mid-stream disconnect is no longer handled by this layer.",
    attemptsLabel: "Retry attempts",
    defAttempts: 3,
    defInterval: "0.5s→1s→2s exponential (capped at 8s)",
    offHint: "-1 = never retry; throw immediately on failure",
  },
  empty: {
    title: "Empty response retry",
    where: "SDK · openai format only",
    trigger:
      "HTTP 200 with a normal stop finish_reason, but the entire response contains no content block — gateway empty frames, dropped thinking fields, and sampling hiccups all look like this.",
    skips: "Empty responses caused by max_tokens truncation do not count (fix those by raising the output limit; resending just hits the same wall again).",
    desc: "Resends the entire prompt, so it is relatively expensive with long contexts; keep the count modest.",
    attemptsLabel: "Retry attempts",
    defAttempts: 2,
    defInterval: "0.5s→1s→2s exponential (capped at 8s)",
    offHint: "-1 = hand the empty response back as-is",
  },
  stream: {
    title: "Same-provider safe window retry",
    where: "This project · before any output is delivered",
    trigger:
      "Problems after the stream is established (a 200 is received): mid-stream disconnect, provider overloaded, in-stream 429 / 5xx error events — and not a single token has been delivered to the caller yet.",
    skips:
      "Quota exhausted (402 / insufficient_quota, handled by polling to switch profiles), context too long (413 / context length, handled by compaction), and deterministic 400 / 401 / 403 / 404 / 422 rejections are all not retried.",
    desc: "Replays the same request on the same profile. Since no output has been delivered, replaying will not duplicate model output or tool execution.",
    attemptsLabel: "Retry attempts",
    defAttempts: 2,
    defInterval: "0.5s→1s exponential (capped at 4s)",
    offHint: "-1 = hand the broken stream directly to the outer intent rerun",
  },
  breaker: {
    title: "Polling breaker",
    where: "This project · process-wide, one global copy",
    trigger:
      "Trips when transient failures (429, 5xx, network errors) accumulate consecutively to the threshold; deterministic failures such as insufficient balance (402), invalid key (401 / 403), and missing model (404) ignore the threshold and trip on the first occurrence.",
    skips: "One success resets the count, so a profile that hiccups occasionally does not slowly accumulate its way to a trip.",
    desc: "After tripping, the profile enters cooldown and polling skips it during that period. State is persisted and survives restarts.",
    attemptsLabel: "Consecutive failures before tripping",
    defAttempts: 3,
    defInterval: "1min→5min→30min gradient",
    offHint: "-1 = transient failures never trip (deterministic failures still trip)",
  },
  intent: {
    title: "Intent rerun",
    where: "This project · process-wide, one global copy",
    trigger:
      "None of the earlier layers caught it: the worker ends with model_error — either inner retries are all exhausted, or the stream broke after output had already been delivered (replaying is unsafe then, so the whole thing must start over).",
    skips: "Quota exhaustion is already handled by polling to switch profiles and is not rerun here; when a task is paused / terminated / entering wrap-up, it yields immediately without consuming backoff time.",
    desc: "Runs the entire intent from scratch. It is the outermost layer, so one rerun multiplies the attempt counts of the inner layers again.",
    attemptsLabel: "Rerun attempts",
    defAttempts: 2,
    defInterval: "Fixed 3s",
    offHint: "-1 = do not rerun; mark the intent directly as blocked",
  },
} satisfies Record<string, LayerMeta>;

type LayerKey = keyof typeof RETRY_LAYERS;

/** Human-readable milliseconds, used only for echo beside the input so nobody has to count zeros. */
function humanMs(ms: number) {
  if (!Number.isFinite(ms) || ms <= 0) return "";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${Number((ms / 1000).toFixed(2))}s`;
  return `${Number((ms / 60_000).toFixed(2))}min`;
}

/** Controlled numeric input: empty string ↔ 0; intermediate states ("-", "1e") stay local without bothering the parent. */
function NumField({
  id,
  value,
  onChange,
  placeholder,
  min,
}: {
  id: string;
  value: number;
  onChange: (n: number) => void;
  placeholder: string;
  min: number;
}) {
  const [text, setText] = React.useState(value === 0 ? "" : String(value));
  // Keep up when the parent swaps in a whole new set of values (policy loaded, profile switched); typing locally does not reach here,
  // because at that point value already equals the parsed local text.
  React.useEffect(() => {
    const incoming = value === 0 ? "" : String(value);
    setText((cur) => (Number(cur || 0) === value ? cur : incoming));
  }, [value]);
  return (
    <Input
      id={id}
      type="number"
      min={min}
      className="w-28 shrink-0"
      value={text}
      placeholder={placeholder}
      onChange={(e) => {
        setText(e.target.value);
        const n = Number(e.target.value);
        onChange(e.target.value.trim() === "" || !Number.isFinite(n) ? 0 : Math.trunc(n));
      }}
    />
  );
}

/** The two knobs of one retry layer. idPrefix keeps the label's htmlFor unique when rendered multiple times on one page. */
export function RetryRuleFields({
  layer,
  idPrefix,
  value,
  onChange,
  compact,
}: {
  layer: LayerKey;
  idPrefix: string;
  value: LLMRetryRule;
  onChange: (r: LLMRetryRule) => void;
  /** true = compact version in the profile drawer: omit the expanded explanation and keep only the "what errors reach this layer" line */
  compact?: boolean;
}) {
  const meta = RETRY_LAYERS[layer];
  const human = humanMs(value.interval_ms);
  return (
    <div className={compact ? "grid gap-2" : "grid gap-3 rounded-lg border p-3"}>
      <div className="grid gap-0.5">
        <div className="flex flex-wrap items-baseline gap-2">
          <Label className="text-sm">{meta.title}</Label>
          <span className="text-muted-foreground text-xs">{meta.where}</span>
        </div>
        {/* Which errors reach this layer, down to status codes — if a knob seems to have no effect, the error probably does not land here at all. */}
        <p className="text-muted-foreground text-xs">
          <span className="font-medium text-foreground">Triggers</span>: {meta.trigger}
        </p>
        {!compact && meta.skips && (
          <p className="text-muted-foreground text-xs">
            <span className="font-medium text-foreground">Does not use this layer</span>: {meta.skips}
          </p>
        )}
        {!compact && <p className="text-muted-foreground text-xs">{meta.desc}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-2">
          <Label htmlFor={`${idPrefix}-${layer}-n`} className="text-muted-foreground text-xs">
            {meta.attemptsLabel}
          </Label>
          <NumField
            id={`${idPrefix}-${layer}-n`}
            min={-1}
            value={value.attempts}
            placeholder={`Default ${meta.defAttempts}`}
            onChange={(n) => onChange({ ...value, attempts: n })}
          />
        </div>
        <div className="flex items-center gap-2">
          <Label htmlFor={`${idPrefix}-${layer}-ms`} className="text-muted-foreground text-xs">
            Interval ms
          </Label>
          <NumField
            id={`${idPrefix}-${layer}-ms`}
            min={0}
            value={value.interval_ms}
            placeholder="Default backoff"
            onChange={(n) => onChange({ ...value, interval_ms: n })}
          />
          <span className="text-muted-foreground text-xs">{human ? `Fixed ${human}` : meta.defInterval}</span>
        </div>
      </div>
      {!compact && <p className="text-muted-foreground text-xs">Empty = use default; {meta.offHint}.</p>}
    </div>
  );
}

/** The three-layer override in the model profile drawer (the three layers tied to the endpoint). */
export function ProfileRetryFields({
  value,
  onChange,
}: {
  value: LLMRetryOverride;
  onChange: (o: LLMRetryOverride) => void;
}) {
  return (
    <div className="grid gap-3 rounded-lg border p-3">
      <div className="grid gap-0.5">
        <Label className="text-sm">Retry override</Label>
        <p className="text-muted-foreground text-xs">
          Applies only to this profile, overriding the global defaults under "Retry and backoff". Empty in any field = follow global; attempts -1 = disable this retry layer;
          a set interval replaces exponential backoff with a fixed interval. The breaker and intent rerun are process-wide and can only be adjusted on the global page.
        </p>
      </div>
      {(["connect", "empty", "stream"] as const).map((k) => (
        <div key={k} className="border-t pt-3 first:border-t-0 first:pt-0">
          <RetryRuleFields
            compact
            layer={k}
            idPrefix="pf"
            value={value[k]}
            onChange={(r) => onChange({ ...value, [k]: r })}
          />
        </div>
      ))}
    </div>
  );
}

/** "Retry and backoff" tab: global defaults for the five layers. */
export function RetryPolicyPanel() {
  const [policy, setPolicy] = React.useState<LLMRetryPolicy>(ZERO_POLICY);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const p = await api.llmRetryPolicy();
      setPolicy({ ...ZERO_POLICY, ...p });
    } catch (e) {
      toast.error(`Failed to load retry policy: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    if (saving) return;
    setSaving(true);
    try {
      // The backend clamps out-of-range values and returns them; refresh directly with the returned values, so what you see is what is stored.
      const saved = await api.saveLLMRetryPolicy(policy);
      setPolicy({ ...ZERO_POLICY, ...saved });
      toast.success("Saved and effective immediately (in-flight calls still use the old parameters)");
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  const set = (k: LayerKey) => (r: LLMRetryRule) => setPolicy((p) => ({ ...p, [k]: r }));

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-dashed p-10 text-muted-foreground text-sm">
        <Loader2Icon className="size-4 animate-spin" /> Loading retry policy…
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="rounded-lg border bg-muted/30 p-3 text-muted-foreground text-xs leading-relaxed">
        A failed model call passes through five retry layers in order, from innermost to outermost:
        <span className="text-foreground"> connect → empty response → same-provider safe window → polling breaker → intent rerun</span>
        . An outer layer only runs after the inner one is exhausted, so the counts
        <span className="text-foreground">multiply</span>
        — max out every layer and one hiccup can burn through dozens of requests.
        Leaving everything empty yields the current defaults, identical to the behavior without this page. The first three layers can be overridden per model profile.
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(Object.keys(RETRY_LAYERS) as LayerKey[]).map((k) => (
          <RetryRuleFields key={k} layer={k} idPrefix="gl" value={policy[k]} onChange={set(k)} />
        ))}
      </div>

      <div className="flex gap-2">
        <Button onClick={save} disabled={saving}>
          {saving ? <Loader2Icon className="animate-spin" /> : <SaveIcon />}
          Save
        </Button>
        <Button variant="outline" onClick={() => setPolicy(ZERO_POLICY)} disabled={saving}>
          Restore all defaults
        </Button>
      </div>
    </div>
  );
}
