from markfold.services.command_parser import parse_command


def test_parse_multiline_init_command() -> None:
    parsed = parse_command("/init\ntitle: 项目A\ngoal: 完成 MVP\nstatus: 进行中")

    assert parsed is not None
    assert parsed.name == "init"
    assert parsed.args["title"] == "项目A"
    assert parsed.args["goal"] == "完成 MVP"
    assert parsed.args["status"] == "进行中"
