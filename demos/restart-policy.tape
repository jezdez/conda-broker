Source demos/_settings.tape

Output demos/restart-policy.gif
Output demos/restart-policy.mp4

Hide
Type `eval "$(pixi shell-hook -s bash -e dev)"`
Enter
Wait /\)/
Type `export PS1="$DEMO_PS1" && export CONDA_BROKER_RUNTIME_DIR=/tmp/conda-broker-demo-restart/runtime && export CONDA_BROKER_LOG_DIR=/tmp/conda-broker-demo-restart/logs && export CONDA_BROKER_DEMO_FLAKY_STATE=/tmp/conda-broker-demo-restart/flaky-state && rm -rf /tmp/conda-broker-demo-restart && python -m pip install -q -e demos/fixtures/demo-provider`
Enter
Wait /\$/
Type `cb stop >/dev/null 2>&1 || true`
Enter
Wait /\$/
Type "clear"
Enter
Wait /\$/
Show

Type "# Start a service that fails once"
Enter
Sleep 500ms
Type@80ms "cb start flaky"
Enter
Wait /\$/
Sleep 3s

Type "# The restart policy brings it back"
Enter
Sleep 500ms
Type@80ms "cb status flaky"
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
