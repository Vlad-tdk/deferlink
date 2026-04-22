"""
Safari Escape Page Generator
Генератор страницы-мостика: IAB → App Store + clipboard handoff

Механизм работы:
1. Пользователь кликает рекламу → Facebook IAB открывает наш URL
2. Сервер детектирует IAB → возвращает эту HTML страницу вместо прямого редиректа
3. JavaScript на странице:
   a) Записывает session_token в буфер обмена (через execCommand — работает в WKWebView)
   b) Делает редирект на App Store через 400ms
4. Пользователь устанавливает приложение
5. Приложение при первом запуске читает буфер обмена → находит токен → 100% матчинг

Fallback цепочка для clipboard:
  navigator.clipboard.writeText()  → Modern API (требует gesture в Safari, работает в IAB)
  document.execCommand('copy')     → Legacy API (работает без gesture в большинстве WKWebView)
  localStorage                     → Если IAB сохраняет его между сессиями (маловероятно)
"""

from typing import Optional


CLIPBOARD_PREFIX = "deferlink"


def generate_escape_page(
    session_token: str,
    app_store_url: str,
    app_name: str = "приложение",
    app_store_id: Optional[str] = None,
    redirect_delay_ms: int = 400,
) -> str:
    """
    Сгенерировать HTML-страницу для выхода из IAB в App Store с clipboard handoff.

    Args:
        session_token:      ID сессии, который нужно передать в приложение
        app_store_url:      URL в App Store (https://apps.apple.com/app/id...)
        app_name:           Название приложения (для текста на странице)
        app_store_id:       App Store ID для meta-тега apple-itunes-app (опционально)
        redirect_delay_ms:  Задержка перед редиректом в мс (время на запись в clipboard)

    Returns:
        Строка с полным HTML документом
    """
    clipboard_value = f"{CLIPBOARD_PREFIX}:{session_token}"
    itunes_meta = (
        f'<meta name="apple-itunes-app" content="app-id={app_store_id}">'
        if app_store_id else ""
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  {itunes_meta}
  <title>Открываем {app_name}…</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
      background: #000;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100dvh;
      padding: 24px;
      -webkit-font-smoothing: antialiased;
    }}

    .card {{
      text-align: center;
      max-width: 320px;
      width: 100%;
      animation: fadeIn .3s ease;
    }}

    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}

    .app-icon {{
      width: 88px;
      height: 88px;
      background: linear-gradient(135deg, #007AFF 0%, #5856D6 100%);
      border-radius: 22px;
      margin: 0 auto 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 44px;
      box-shadow: 0 8px 32px rgba(0,122,255,.35);
    }}

    h1 {{
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -.3px;
      margin-bottom: 10px;
    }}

    p {{
      font-size: 15px;
      line-height: 1.55;
      color: rgba(255,255,255,.55);
      margin-bottom: 32px;
    }}

    .spinner {{
      width: 44px;
      height: 44px;
      border: 3px solid rgba(255,255,255,.12);
      border-top-color: #007AFF;
      border-radius: 50%;
      margin: 0 auto 16px;
      animation: spin .75s linear infinite;
    }}

    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

    .status {{
      font-size: 13px;
      color: rgba(255,255,255,.3);
      min-height: 18px;
      transition: color .2s;
    }}

    .status.ok {{ color: rgba(52,199,89,.8); }}
  </style>
</head>
<body>
  <div class="card">
    <div class="app-icon">📱</div>
    <h1>Переходим в App Store</h1>
    <p>Сейчас откроется App Store<br>для установки {app_name}</p>
    <div class="spinner"></div>
    <div class="status" id="st">Подготовка…</div>
  </div>

  <script>
  (function () {{
    "use strict";

    var TOKEN   = {repr(clipboard_value)};
    var DEST    = {repr(app_store_url)};
    var DELAY   = {redirect_delay_ms};
    var statusEl = document.getElementById('st');

    // ── Запись в буфер обмена ────────────────────────────────────────────────

    function markOk() {{
      statusEl.textContent = '✓ Контекст сохранён';
      statusEl.className = 'status ok';
    }}

    function execCommandCopy(text) {{
      try {{
        var el = document.createElement('input');
        el.setAttribute('readonly', '');
        el.value = text;
        el.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0;';
        document.body.appendChild(el);
        el.focus();
        el.setSelectionRange(0, el.value.length);
        var ok = document.execCommand('copy');
        document.body.removeChild(el);
        if (ok) markOk();
      }} catch (e) {{ /* silent */ }}
    }}

    function writeClipboard() {{
      // Метод 1: Современный Clipboard API
      if (window.navigator && window.navigator.clipboard && window.navigator.clipboard.writeText) {{
        window.navigator.clipboard.writeText(TOKEN)
          .then(markOk)
          .catch(function () {{ execCommandCopy(TOKEN); }});
      }} else {{
        // Метод 2: execCommand (работает без gesture в большинстве WKWebView)
        execCommandCopy(TOKEN);
      }}
    }}

    // Метод 3: localStorage как дополнительный fallback
    try {{ localStorage.setItem('__dl_token', TOKEN); }} catch (e) {{}}

    // Запускаем все методы
    writeClipboard();
    statusEl.textContent = 'Открываем App Store…';

    // ── Редирект ─────────────────────────────────────────────────────────────
    setTimeout(function () {{
      window.location.href = DEST;
    }}, DELAY);

  }})();
  </script>
</body>
</html>"""


def build_app_store_url(app_store_id: str) -> str:
    """Сформировать canonical URL в App Store."""
    return f"https://apps.apple.com/app/id{app_store_id}"
