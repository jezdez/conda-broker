Source demos/_settings.tape

Output demos/provider-plugin.gif

Type "# A provider exposes conda_broker_services()"
Enter
Sleep 500ms
Type@80ms "sed -n '1,80p' demos/fixtures/demo-provider/demo_provider/broker.py"
Enter
Wait /\$/
Sleep 2s

Type "# Install the provider package"
Enter
Sleep 500ms
Type@80ms "python -m pip install -q -e demos/fixtures/demo-provider"
Enter
Wait /\$/

Type "# The broker registry discovers its services"
Enter
Sleep 500ms
Type@80ms "cb list"
Enter
Wait /\$/
Sleep 2s
