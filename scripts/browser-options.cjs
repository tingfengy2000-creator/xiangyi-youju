/* Shared Playwright launch options.
 * BROWSER_EXECUTABLE: explicit browser binary for this machine (not stored in the repository).
 * BROWSER_CHANNEL: installed browser channel such as msedge.
 * Without either, Playwright's own Chromium is used unless a caller passes a default channel.
 */
function browserOptions(defaultChannel) {
  const options = { headless: true };
  if (process.env.BROWSER_EXECUTABLE) options.executablePath = process.env.BROWSER_EXECUTABLE;
  else if (process.env.BROWSER_CHANNEL || defaultChannel) options.channel = process.env.BROWSER_CHANNEL || defaultChannel;
  return options;
}

module.exports = { browserOptions };
