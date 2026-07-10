Source demos/_settings.tape

Output demos/health-check.gif

Type "# Start a service whose first health check fails"
Enter
Sleep 500ms
Type@80ms "cb wait healthcheck --start --timeout 10"
Enter
Wait /\$/
Sleep 1s

Type "# Events record the health failure and restart"
Enter
Sleep 500ms
Type@80ms "cb events --lines 8"
Enter
Wait /\$/
Sleep 1s

Type "# Logs continue after restart"
Enter
Sleep 500ms
Type@80ms "cb logs healthcheck --lines 6"
Enter
Wait /\$/
Sleep 2s

Hide
Type "cb stop"
Enter
Wait /\$/
