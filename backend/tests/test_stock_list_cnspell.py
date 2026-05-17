from __future__ import annotations

from app.modules.market_data import data_source


def test_to_cnspell_uses_pypinyin_when_available(monkeypatch) -> None:
    class _Style:
        FIRST_LETTER = object()

    def _fake_lazy_pinyin(text: str, style=None, strict=False, errors='ignore'):  # noqa: ARG001
        mapping = {
            '平': ['p'],
            '安': ['a'],
            '银': ['y'],
            '行': ['h'],
        }
        return mapping[text]

    monkeypatch.setattr(data_source, 'Style', _Style)
    monkeypatch.setattr(data_source, 'lazy_pinyin', _fake_lazy_pinyin)

    assert data_source._to_cnspell('平安银行') == 'PAYH'


def test_to_cnspell_filters_non_alpha_letters(monkeypatch) -> None:
    class _Style:
        FIRST_LETTER = object()

    def _fake_lazy_pinyin(text: str, style=None, strict=False, errors='ignore'):  # noqa: ARG001
        return []

    monkeypatch.setattr(data_source, 'Style', _Style)
    monkeypatch.setattr(data_source, 'lazy_pinyin', _fake_lazy_pinyin)

    assert data_source._to_cnspell('PingAn-Bank') == 'PINGANBANK'


def test_to_cnspell_keeps_ascii_letters_in_original_position(monkeypatch) -> None:
    class _Style:
        FIRST_LETTER = object()

    def _fake_lazy_pinyin(text: str, style=None, strict=False, errors='ignore'):  # noqa: ARG001
        mapping = {
            '中': ['z'],
            '际': ['j'],
            '控': ['k'],
            '股': ['g'],
        }
        return mapping.get(text, [])

    monkeypatch.setattr(data_source, 'Style', _Style)
    monkeypatch.setattr(data_source, 'lazy_pinyin', _fake_lazy_pinyin)

    assert data_source._to_cnspell('中A际B控股') == 'ZAJBKG'


def test_mairui_rows_to_stock_list_frame_populates_cnspell(monkeypatch) -> None:
    class _Style:
        FIRST_LETTER = object()

    mapping = {
        '平': ['p'],
        '安': ['a'],
        '银': ['y'],
        '行': ['h'],
        '中': ['z'],
        '际': ['j'],
        '旭': ['x'],
        '创': ['c'],
    }

    def _fake_lazy_pinyin(text: str, style=None, strict=False, errors='ignore'):  # noqa: ARG001
        return mapping[text]

    monkeypatch.setattr(data_source, 'Style', _Style)
    monkeypatch.setattr(data_source, 'lazy_pinyin', _fake_lazy_pinyin)

    df = data_source._mairui_rows_to_stock_list_frame(
        [
            {'dm': '000001.SZ', 'mc': '平安银行'},
            {'dm': '300308.SZ', 'mc': '中际旭创'},
        ]
    )

    assert list(df['cnspell']) == ['PAYH', 'ZJXC']
