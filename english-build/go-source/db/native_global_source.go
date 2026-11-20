package db

import "database/sql"

// NativeGlobalSourceAvailable mirrors Server.loadLLMConfig/ActiveProfile exactly:
// the default row wins only with a nonempty key; otherwise ENV is used. Query
// errors are denied rather than mistaken for absent configuration. The server
// computes key presence; profile credentials never cross the SQL boundary.
func (d *DB) NativeGlobalSourceAvailable() (bool, error) {
	var keyed bool
	err := d.QueryRow(`SELECT COALESCE(api_key,'') <> '' FROM llm_profiles WHERE is_default LIMIT 1`).Scan(&keyed)
	if err == sql.ErrNoRows {
		return true, nil
	}
	if err != nil {
		return false, err
	}
	return !keyed, nil
}
