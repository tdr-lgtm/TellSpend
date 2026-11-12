"""
The HTML for TellSpend's emails, in the app's brand (deep green and lime).

Written for mail apps, not browsers: tables for layout, every style inline
(Gmail drops <style> blocks), no images (they're blocked by default, and
SVG never shows), and a plain-text version is always sent alongside. The
logo is a lime tile with a rupee sign drawn in HTML.
"""

from html import escape

GREEN = "#0F3D2E"
LIME = "#C8F169"
INK = "#0F172A"
MUTED = "#64748B"
LINE = "#E2E8F0"
PAGE = "#F1F5F4"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _layout(*, preheader: str, heading: str, body: str) -> str:
    """The shared frame: brand bar, white card, footer."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{escape(heading)}</title>
</head>
<body style="margin:0;padding:0;background:{PAGE};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAGE};">
<tr><td align="center" style="padding:32px 16px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;">

    <tr><td style="background:{GREEN};border-radius:16px 16px 0 0;padding:22px 28px;">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="width:34px;height:34px;background:{LIME};border-radius:10px;text-align:center;vertical-align:middle;font-family:{FONT};font-size:19px;font-weight:700;color:{GREEN};line-height:34px;">&#8377;</td>
        <td style="padding-left:10px;font-family:{FONT};font-size:17px;font-weight:600;color:#FFFFFF;letter-spacing:-0.2px;">TellSpend</td>
      </tr></table>
    </td></tr>

    <tr><td style="background:#FFFFFF;border-radius:0 0 16px 16px;padding:32px 28px 30px;font-family:{FONT};color:{INK};">
      <h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;font-weight:700;letter-spacing:-0.3px;color:{INK};">{escape(heading)}</h1>
      {body}
    </td></tr>

    <tr><td style="padding:22px 28px 0;font-family:{FONT};font-size:12px;line-height:1.6;color:{MUTED};text-align:center;">
      TellSpend &middot; Say what you spent. We&rsquo;ll do the maths.<br>
      This is an automatic email about your account; replies aren&rsquo;t read.
    </td></tr>

  </table>
</td></tr>
</table>
</body>
</html>"""


def _p(html: str, *, muted: bool = False, small: bool = False) -> str:
    size = "13px" if small else "15px"
    color = MUTED if muted else INK
    return f'<p style="margin:0 0 16px;font-size:{size};line-height:1.6;color:{color};">{html}</p>'


def verification_email(name: str, code: str, minutes: int, link: str) -> str:
    """
    Explanation:
        The email with the 6-digit code that verifies an address, and a
        button that verifies it in one click (no copying: mail apps can't
        copy to the clipboard).

    Parameters:
        name: The user's name.
        code: The code.
        minutes: How long it works.
        link: The verify page with the email and code filled in.

    Returns:
        The HTML.
    """
    # Each digit in its own box. (The subject, preview and plain-text
    # version keep the code as one number, for apps that read it.)
    digits = "".join(
        f'<td style="padding:0 3px;"><div style="width:42px;height:52px;line-height:52px;background:#FFFFFF;'
        f"border:1px solid #DDEFB5;border-radius:10px;text-align:center;font-family:'SFMono-Regular',Menlo,"
        f'Consolas,monospace;font-size:26px;font-weight:700;color:{GREEN};">{escape(digit)}</div></td>'
        for digit in code
    )
    url = escape(link, quote=True)
    box = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 20px;">'
        f'<tr><td align="center" style="background:#F4FBE6;border:1px solid #DDEFB5;border-radius:16px;padding:22px 12px 24px;">'
        f'<div style="font-family:{FONT};font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;'
        f'color:{MUTED};margin-bottom:14px;">One-time password</div>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>{digits}</tr></table>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:20px;"><tr>'
        f'<td style="background:{GREEN};border-radius:12px;">'
        f'<a href="{url}" style="display:inline-block;padding:12px 26px;font-family:{FONT};font-size:15px;'
        f'font-weight:600;color:{LIME};text-decoration:none;border-radius:12px;">Verify my email</a>'
        f"</td></tr></table>"
        f'<div style="font-family:{FONT};font-size:12px;color:{MUTED};margin-top:10px;">'
        f"One click, no copying. Or type the code in TellSpend.</div>"
        f"</td></tr></table>"
    )
    body = (
        # Worded like the one-time-password emails mail apps recognise
        # ("Your One-Time Password (OTP) ... is: 123456"), so Gmail can
        # offer its "Copy code" card. Whether it does is Gmail's decision.
        _p(f"Hi {escape(name)},")
        + _p("Your One-Time Password (OTP) to verify your TellSpend email address is:")
        + box
        + _p(f"This OTP is valid for <strong>{minutes} minutes</strong> and works only once. "
             "Don&rsquo;t share it with anyone.", muted=True, small=True)
        + _p("Didn&rsquo;t sign up for TellSpend? You can ignore this email; nothing happens without the code.",
             muted=True, small=True)
    )
    return _layout(preheader=f"Your TellSpend OTP is {code}", heading="Your verification code", body=body)


def password_reset_email(name: str, link: str, minutes: int) -> str:
    """
    Explanation:
        The email with the link to choose a new password.

    Parameters:
        name: The user's name.
        link: The reset link.
        minutes: How long it works.

    Returns:
        The HTML.
    """
    url = escape(link, quote=True)
    button = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 24px;"><tr>'
        f'<td style="background:{GREEN};border-radius:12px;">'
        f'<a href="{url}" style="display:inline-block;padding:13px 26px;font-family:{FONT};font-size:15px;'
        f'font-weight:600;color:{LIME};text-decoration:none;border-radius:12px;">Choose a new password</a>'
        f"</td></tr></table>"
    )
    fallback = (
        f'<p style="margin:0 0 20px;font-size:12px;line-height:1.6;color:{MUTED};">'
        f"Button not working? Paste this link into your browser:<br>"
        f'<a href="{url}" style="color:{GREEN};word-break:break-all;">{escape(link)}</a></p>'
    )
    note = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'<tr><td style="border-top:1px solid {LINE};padding-top:16px;font-size:13px;line-height:1.6;color:{MUTED};">'
        f"Didn&rsquo;t ask for this? Ignore this email: your password stays the same, and the link "
        f"stops working on its own.</td></tr></table>"
    )
    body = (
        _p(f"Hi {escape(name)},")
        + _p("Someone asked to reset the password for your TellSpend account. If it was you, choose a new one:")
        + button
        + _p(f"The link works once, for <strong>{minutes} minutes</strong>.", muted=True, small=True)
        + fallback
        + note
    )
    return _layout(preheader="Choose a new password for TellSpend", heading="Reset your password", body=body)
