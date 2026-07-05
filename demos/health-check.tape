Source demos/_settings.tape

Output demos/health-check.gif
Output demos/health-check.mp4

Hide
Type `eval "$(pixi shell-hook -s bash -e dev)"`
Enter
Wait /\)/
Type `export PS1="$DEMO_PS1" && export CONDA_BROKER_RUNTIME_DIR=/tmp/conda-broker-demo-health/runtime && export CONDA_BROKER_LOG_DIR=/tmp/conda-broker-demo-health/logs && export CONDA_BROKER_DEMO_HEALTH_STATE=/tmp/conda-broker-demo-health/health-state && rm -rf /tmp/conda-broker-demo-health && python -m pip install -q -e demos/fixtures/demo-provider`
Enter
Wait /\$/
Type `cb stop >/dev/null 2>&1 || true`
Enter
Wait /\$/
Type "clear"
Enter
Wait /\$/
Show

Type "# Start a service with an exec health check"
Enter
Sleep 500ms
Type@80ms "cb start healthcheck"
Enter
Wait /\$/
Sleep 3s
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# The failed check restarts the service"
Enter
Sleep 500ms
Type@80ms "cb status healthcheck"
Enter
Wait /\$/
Sleep 1s
Hide
Type "clear"
Enter
Wait /\$/
Show

Type "# Events record the health failure and restart"
Enter
Sleep 500ms
Type@80ms "cb events --lines 8"
Enter
Wait /\$/
Sleep 1s
Hide
Type "clear"
Enter
Wait /\$/
Show

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
