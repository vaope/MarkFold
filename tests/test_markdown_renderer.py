from markfold.markdown.renderer import MANAGED_BLOCK_END, MANAGED_BLOCK_START, upsert_managed_block


def test_upsert_managed_block_replaces_existing_block() -> None:
    original = (
        "# Demo\n\n"
        f"{MANAGED_BLOCK_START}\nold\n{MANAGED_BLOCK_END}\n"
    )
    updated = upsert_managed_block(original, f"{MANAGED_BLOCK_START}\nnew\n{MANAGED_BLOCK_END}\n")

    assert "new" in updated
    assert "\nold\n" not in updated
