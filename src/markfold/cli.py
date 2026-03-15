from __future__ import annotations

import mimetypes
from datetime import date, timedelta
from pathlib import Path

import typer

from markfold.domain.enums import Channel
from markfold.repositories import SessionLocal, init_database
from markfold.services import MarkFoldService, UploadedAttachment
from markfold.services.presenters import format_submission_result


app = typer.Typer(help="MarkFold 对话式命令行助手")
todo_app = typer.Typer(help="Todo commands")
app.add_typer(todo_app, name="todo")

def _with_service() -> MarkFoldService:
    init_database()
    session = SessionLocal()
    return MarkFoldService(session)


def _assistant_say(message: str) -> None:
    for line in message.splitlines():
        typer.echo(f"助手 > {line}")


def _parse_attach_payload(raw_text: str) -> tuple[str, str]:
    payload = raw_text.removeprefix("/attach").strip()
    if not payload:
        raise ValueError("请在 /attach 后提供文件路径。")
    if payload.startswith('"'):
        end_quote = payload.find('"', 1)
        if end_quote == -1:
            raise ValueError('带空格的路径请使用英文双引号包裹，例如 /attach "C:\\tmp\\a b.png"。')
        file_path = payload[1:end_quote].strip()
        note = payload[end_quote + 1 :].strip()
        return file_path, note
    file_path, _, note = payload.partition(" ")
    return file_path.strip(), note.strip()


def _load_attachment(path_value: str) -> UploadedAttachment:
    attachment_path = Path(path_value).expanduser()
    if not attachment_path.is_absolute():
        attachment_path = Path.cwd() / attachment_path
    if not attachment_path.exists():
        raise FileNotFoundError(f"附件不存在：{attachment_path}")
    mime_type, _ = mimetypes.guess_type(attachment_path.name)
    return UploadedAttachment(
        filename=attachment_path.name,
        content_type=mime_type or "application/octet-stream",
        content=attachment_path.read_bytes(),
    )


def _format_result(service: MarkFoldService, result, context_key: str) -> str:
    return format_submission_result(service, result, context_key)


def _show_chat_help() -> None:
    _assistant_say(
        "\n".join(
            [
                "当前是对话模式，你可以直接输入自然语言，也可以使用命令。",
                "工作流命令：/init、/finish-init、/cancel-init、/use、/todo、/done、/status",
                "会话命令：/help、/attach <路径>、/todos、/workitems、/yesterday、/exit",
                "提示：/init 会开启一个由 LLM 引导的初始化会话，逐步补全首版文档。",
                '示例：/init 项目A',
                "示例：这个项目的目标是先把 MVP 跑起来",
                "示例：当前已知待办是补日志、补监控",
                "示例：/finish-init",
                '示例：今天把接口联调跑通了，还要补错误处理',
                '示例：/attach "C:\\\\tmp\\\\screenshot.png"',
            ]
        )
    )


def _show_work_items(service: MarkFoldService) -> None:
    work_items = service.list_work_items()
    if not work_items:
        _assistant_say("当前还没有工作项。你可以先输入 /init 项目A，进入渐进式初始化。")
        return
    lines = ["当前工作项列表："]
    for item in work_items[:20]:
        lines.append(f"- {item.title} [{item.status}] ({item.id})")
    _assistant_say("\n".join(lines))


def _show_todos(service: MarkFoldService, context_key: str) -> None:
    try:
        status = service.status(None, context_key=context_key)
        if status.open_todos:
            lines = [f"{status.work_item.title} 的未完成 Todo："]
            for todo in status.open_todos:
                lines.append(f"- {todo.content}")
            _assistant_say("\n".join(lines))
            return
    except ValueError:
        pass

    todos = service.list_open_todos()
    if not todos:
        _assistant_say("当前没有未完成 Todo。")
        return
    lines = ["当前所有未完成 Todo："]
    for todo in todos[:20]:
        lines.append(f"- {todo.work_item_id}: {todo.content}")
    _assistant_say("\n".join(lines))


def _show_yesterday(service: MarkFoldService) -> None:
    summary = service.daily_summary(date.today() - timedelta(days=1))
    if not summary:
        _assistant_say("昨天没有结构化记录。")
        return
    lines = ["昨天的回顾："]
    for item in summary:
        lines.append(f"- {item.title}")
        for value in item.progress:
            lines.append(f"  进展：{value}")
        for value in item.completed:
            lines.append(f"  完成：{value}")
        for value in item.risks:
            lines.append(f"  风险：{value}")
    _assistant_say("\n".join(lines))


def _chat_loop(context_key: str = "cli:chat", kickoff_text: str | None = None) -> None:
    service = _with_service()
    try:
        _assistant_say("已进入 MarkFold 对话模式。直接输入你的记录即可。输入 /help 查看帮助，输入 /exit 退出。")
        try:
            current = service.status(None, context_key=context_key)
            _assistant_say(f"当前上下文工作项：{current.work_item.title}")
        except ValueError:
            _assistant_say("当前还没有激活的工作项。你可以先输入 /init 项目A 开始初始化，或直接输入 /use 项目名。")

        if kickoff_text:
            try:
                result = service.handle_input(
                    raw_text=kickoff_text,
                    channel=Channel.CLI,
                    context_key=context_key,
                )
                _assistant_say(_format_result(service, result, context_key))
            except ValueError as exc:
                _assistant_say(str(exc))

        while True:
            try:
                user_text = input("你 > ").strip()
            except EOFError:
                typer.echo()
                _assistant_say("对话已结束。")
                break
            except KeyboardInterrupt:
                typer.echo()
                _assistant_say("已退出对话。")
                break

            if not user_text:
                continue

            if user_text in {"/exit", "/quit"}:
                _assistant_say("已退出对话。")
                break
            if user_text == "/help":
                _show_chat_help()
                continue
            if user_text == "/workitems":
                _show_work_items(service)
                continue
            if user_text == "/todos":
                _show_todos(service, context_key)
                continue
            if user_text == "/yesterday":
                _show_yesterday(service)
                continue
            if user_text.startswith("/attach"):
                try:
                    path_value, note = _parse_attach_payload(user_text)
                    attachment = _load_attachment(path_value)
                    result = service.handle_input(
                        raw_text=note,
                        channel=Channel.CLI,
                        context_key=context_key,
                        uploaded_attachments=[attachment],
                    )
                    _assistant_say(_format_result(service, result, context_key))
                except (ValueError, FileNotFoundError) as exc:
                    _assistant_say(str(exc))
                continue

            try:
                result = service.handle_input(
                    raw_text=user_text,
                    channel=Channel.CLI,
                    context_key=context_key,
                )
                _assistant_say(_format_result(service, result, context_key))
            except ValueError as exc:
                _assistant_say(str(exc))
    finally:
        service.session.close()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _chat_loop()


@app.command()
def chat(
    context_key: str = typer.Option("cli:chat", help="Conversation context key"),
) -> None:
    _chat_loop(context_key=context_key)


@app.command()
def init(
    title: str,
    goal: str = typer.Option("", help="Optional goal"),
    status: str = typer.Option("active", help="Initial status"),
    context_key: str = typer.Option("cli:init", help="Context key"),
) -> None:
    kickoff_lines = ["/init", f"title: {title}"]
    if goal:
        kickoff_lines.append(f"goal: {goal}")
    if status:
        kickoff_lines.append(f"status: {status}")
    _chat_loop(context_key=context_key, kickoff_text="\n".join(kickoff_lines))


@app.command(name="import")
def import_command(
    path: Path,
    context_key: str = typer.Option("cli:default", help="Context key"),
) -> None:
    service = _with_service()
    try:
        work_item = service.import_work_item(str(path), context_key=context_key)
        typer.echo(f"Imported {work_item.title} ({work_item.id})")
    finally:
        service.session.close()


@app.command()
def send(
    text: str = typer.Argument("", help="Raw text or slash command"),
    context_key: str = typer.Option("cli:default", help="Context key"),
    work_item_id: str | None = typer.Option(None, help="Explicit work item id"),
    file: list[Path] = typer.Option(None, "--file", help="Attachment path"),
) -> None:
    service = _with_service()
    try:
        attachments = [
            UploadedAttachment(
                filename=path.name,
                content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                content=path.read_bytes(),
            )
            for path in file or []
        ]
        result = service.handle_input(
            raw_text=text,
            channel=Channel.CLI,
            context_key=context_key,
            uploaded_attachments=attachments,
            explicit_work_item_id=work_item_id,
        )
        typer.echo(_format_result(service, result, context_key))
    finally:
        service.session.close()


@app.command()
def status(
    title_or_id: str | None = typer.Argument(None),
    context_key: str = typer.Option("cli:default", help="Context key"),
) -> None:
    service = _with_service()
    try:
        result = service.status(title_or_id, context_key=context_key)
        typer.echo(f"{result.work_item.title} [{result.work_item.status}]")
        if result.open_todos:
            typer.echo("Open todos:")
            for todo in result.open_todos:
                typer.echo(f"- {todo.content}")
        if result.recent_events:
            typer.echo("Recent events:")
            for event in result.recent_events[:5]:
                typer.echo(f"- {event.type}: {event.content}")
    finally:
        service.session.close()


@app.command()
def yesterday(
    target_date: str | None = typer.Option(None, help="Date to query in YYYY-MM-DD format"),
) -> None:
    service = _with_service()
    try:
        parsed_date = date.fromisoformat(target_date) if target_date else (date.today() - timedelta(days=1))
        summary = service.daily_summary(parsed_date)
        for item in summary:
            typer.echo(item.title)
            for value in item.progress:
                typer.echo(f"- progress: {value}")
            for value in item.completed:
                typer.echo(f"- completed: {value}")
            for value in item.risks:
                typer.echo(f"- risk: {value}")
    finally:
        service.session.close()


@app.command()
def worker(limit: int = typer.Option(20, help="Max jobs to process")) -> None:
    service = _with_service()
    try:
        processed = service.run_worker(limit=limit)
        typer.echo(f"Processed {processed} job(s)")
    finally:
        service.session.close()


@todo_app.command("list")
def list_todos(work_item_id: str | None = typer.Option(None, help="Optional work item id")) -> None:
    service = _with_service()
    try:
        todos = service.list_open_todos(work_item_id)
        for todo in todos:
            typer.echo(f"{todo.work_item_id}: {todo.content}")
    finally:
        service.session.close()
