/** German text for a mailbox reason code. The API answers English codes (`unreachable`,
 * `certificate`, `login`, `protocol`, `folder`, `no key`, `no password`, `password unreadable`),
 * never the server's own words, and the UI says what to do about each. */
const REASONS: Record<string, string> = {
  unreachable: 'Der Server ist nicht erreichbar. Prüfe Server und Port.',
  certificate: 'Das Zertifikat des Servers wurde nicht angenommen. Prüfe den Namen des Servers.',
  login: 'Der Server hat die Anmeldung abgelehnt. Prüfe Benutzername und Passwort.',
  protocol: 'Der Server hat nicht wie ein IMAP-Server mit TLS geantwortet. Prüfe den Port, meist ist es 993.',
  folder: 'Ein Ordner ließ sich nicht öffnen. Prüfe die Auswahl der Ordner.',
  'no key': 'Es ist kein Schlüssel für das Passwort eingerichtet. Wie du einen einrichtest, steht in der README.',
  'no password': 'Es ist kein Passwort gespeichert. Gib das Passwort ein.',
  'password unreadable': 'Das gespeicherte Passwort lässt sich nicht lesen, der Schlüssel passt nicht dazu. Gib das Passwort noch einmal ein.',
}

/** The text for `reason`; an unknown code gets a general sentence. */
export const mailboxReason = (reason: string | null | undefined): string =>
  REASONS[reason ?? ''] ?? 'Das Postfach konnte nicht gelesen werden.'

/** German text for a failed reading of an oversized mail, by the API's error. */
export function oversizedFailure(error: string | null): string {
  if (error === 'screening failed') return 'Die Inhaltsprüfung hat nicht geantwortet, deshalb hat kein Modell die Mail gelesen. Hake sie noch einmal an, um es erneut zu versuchen.'
  if (error === 'finder failed') return 'Das Modell hat nicht geantwortet. Hake die Mail noch einmal an, um es erneut zu versuchen.'
  return 'Die Mail konnte nicht gelesen werden. Hake sie noch einmal an, um es erneut zu versuchen.'
}
