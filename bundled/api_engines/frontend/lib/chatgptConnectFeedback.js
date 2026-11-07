/* What the ChatGPT subscription row is allowed to show in red.

   An error belongs to the ACTION the user just took (Connect / Import /
   Disconnect) — never to the mount: a wizard that greets a first-time user with
   "✗ Network error" under an engine he has not touched reads as a broken app,
   not as a request that failed. So the row stores {action, message} and only an
   error carrying the action that produced it renders; a state fetch that fails
   on its own can never reach the screen. */
export function connectFeedback(err) {
  if (!err || !err.action || !err.message) return null
  return err.message
}
