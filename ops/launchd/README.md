# launchd helpers

These files are **macOS LaunchAgents** that can be installed to run parts of this project on a schedule.

## com.smiggy.papertrader.plist

This LaunchAgent runs a Python script every 180 seconds and logs to `paper_trader.log`.

Current configured script path (in the plist):

- `/Users/guybailey/.openclaw/workspace/trading/trader.py`

If you want to version-control the script inside this repo (recommended), update the plist to point at:

- `/Users/guybailey/.openclaw/workspace/crypto-paper/trading/trader.py`

Then reload launchd:

```bash
launchctl bootout gui/$UID ~/Library/LaunchAgents/com.smiggy.papertrader.plist || true
cp ops/launchd/com.smiggy.papertrader.plist ~/Library/LaunchAgents/com.smiggy.papertrader.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.smiggy.papertrader.plist
launchctl kickstart -k gui/$UID/com.smiggy.papertrader
```

(Adjust paths/usernames as needed.)
