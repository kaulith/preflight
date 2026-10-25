app_name = "upgrade_probe"
app_title = "Upgrade Probe"
app_publisher = "Kaushal Shriwas"
app_description = "Deliberate v15 API uses, to measure what an upgrade actually breaks"
app_email = "64089478+kaulith@users.noreply.github.com"
app_license = "mit"

leaderboards = "upgrade_probe.probes.get_leaderboards"

has_permission = {"ToDo": "upgrade_probe.permissions.todo_has_permission"}

override_doctype_class = {"ToDo": "upgrade_probe.overrides.ProbeToDo"}
