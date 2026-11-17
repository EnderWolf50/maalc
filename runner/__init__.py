"""The runner (#812, spec #811 執行器): runs a task list on MaaFramework with the bot as its agent, driven over a
JSON-lines protocol on stdin and stdout (protocol.py). It ships in the zip beside agent/ and runs on the zip's Python:
`python/python.exe runner/__main__.py`. Every caller goes through it: the settings window, tools/live/bot.py run and
the daily task."""
