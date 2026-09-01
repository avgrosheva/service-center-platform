/**
 * Parses the backend's flat validation-error string into per-field
 * messages. Confirmed directly against the running backend (Milestone 19's
 * `RequestValidationError` handler, app/core/exceptions.py): each field's
 * error is `"<field>: <message>"`, multiple fields joined by `"; "` — e.g.
 * `"full_name: Field required; phone: Value error, phone must contain at
 * least 7 digits"`. Field names are the schema's own top-level field
 * names, so they map directly onto form input names.
 *
 * Only call this for an `ApiError` whose `kind` is `'validation'` — other
 * error kinds' `detail` strings (a 404's "No customer ... in this
 * organization", a 403, a 500's generic message) don't follow this shape
 * and shouldn't be parsed as field errors.
 */
export function parseFieldErrors(detail: string): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const segment of detail.split('; ')) {
    const separatorIndex = segment.indexOf(': ');
    if (separatorIndex === -1) continue;
    fields[segment.slice(0, separatorIndex)] = segment.slice(separatorIndex + 2);
  }
  return fields;
}
