from preflight.models import meets_severity


def test_a_severity_meets_itself_and_everything_below_it():
	assert meets_severity("error", "error")
	assert meets_severity("error", "warning")
	assert meets_severity("warning", "info")


def test_a_lower_severity_does_not_meet_a_higher_one():
	assert not meets_severity("warning", "error")
	assert not meets_severity("info", "warning")
