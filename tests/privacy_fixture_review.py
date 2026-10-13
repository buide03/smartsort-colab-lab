"""Simulate manual review of known public fixtures in training E2E tests."""


def upload_public_fixture(page, path):
    page.set_input_files('#uploadInput', str(path))
    while True:
        page.wait_for_function("""() => !uploading ||
          !!document.querySelector('.privacy-dialog[open] [data-review]:not([disabled])')""", timeout=90000)
        if not page.evaluate('uploading'):
            break
        page.locator('[data-review-label]').select_option('exclude')
        page.locator('[data-review]').check()
        page.locator('[data-accept]').click()
