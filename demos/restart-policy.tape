Source demos/_settings.tape

Output demos/restart-policy.gif

Type "# Start a service that fails once"
Enter
Sleep 500ms
Type@80ms "cb start flaky >/dev/null"
Enter
Wait /\$/
Sleep 3s

Type "# Wait for the recovered process"
Enter
Sleep 500ms
Type@80ms "cb wait flaky --timeout 10"
Enter
Wait /\$/
Sleep 1s

Type "# Events show the crash and scheduled restart"
Enter
Sleep 500ms
Type@80ms "cb events --lines 8"
Enter
Wait /\$/
Sleep 2s

Hide
Type "cb stop"
Enter
Wait /\$/
