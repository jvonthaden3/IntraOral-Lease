from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort

import calc
import db
import mailer
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY


@app.template_filter("usd")
def usd_filter(value):
    try:
        return "${:,.2f}".format(float(value))
    except (TypeError, ValueError):
        return value


@app.template_filter("pct1")
def pct1_filter(value):
    try:
        return "{:.1f}%".format(float(value) * 100)
    except (TypeError, ValueError):
        return value


@app.template_filter("mask_ssn")
def mask_ssn_filter(value):
    if not value:
        return ""
    digits = "".join(c for c in str(value) if c.isdigit())
    return f"***-**-{digits[-4:]}" if len(digits) >= 4 else "***"


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# Public calculator -- no login. A brand-new visitor gets a blank lab profile
# to fill in; a returning lab uses the /lab/<token> link they were given,
# which links back here with ?lab=<token> so their info is pre-filled and
# every proposal they generate attaches to their own (and only their own)
# lab record.
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    lab_token = request.args.get("lab", "")
    lab = db.get_lab_by_token(lab_token) if lab_token else None
    settings = db.get_settings()
    lab_monthly_payment = calc.pmt(settings["lab_apr"], settings["lab_term"], settings["lab_financed"])
    return render_template("index.html", lab=lab, proposal=None, settings=settings, lab_monthly_payment=lab_monthly_payment, supplier=config.SUPPLIER)


# ---------------------------------------------------------------------------
# Re-open an existing proposal on the calculator page, pre-filled with its
# own saved numbers, so a lab can correct or adjust a deal without guessing
# at what it originally entered. Saving here updates that SAME proposal (and
# keeps its link) instead of creating a new one.
# ---------------------------------------------------------------------------
@app.route("/p/<token>/edit")
def edit_proposal(token):
    p, lab = _get_proposal_and_lab_or_404(token)
    settings = db.get_settings()
    lab_monthly_payment = calc.pmt(settings["lab_apr"], settings["lab_term"], settings["lab_financed"])
    return render_template("index.html", lab=lab, proposal=p, settings=settings, lab_monthly_payment=lab_monthly_payment, supplier=config.SUPPLIER)


@app.route("/api/calc", methods=["POST"])
def api_calc():
    """Live calculation, used for the on-page preview before anything is saved."""
    inputs = request.get_json(force=True) or {}
    settings = db.get_settings()
    inputs["equipment_cost"] = settings["equipment_cost"]
    inputs["lab_down_payment"] = settings["lab_down_payment"]
    inputs["lab_apr"] = settings["lab_apr"]
    inputs["lab_term"] = settings["lab_term"]
    inputs["round_to"] = settings["round_to"]
    results = calc.compute(inputs)
    return jsonify(results)


@app.route("/api/labs", methods=["POST"])
def api_create_lab():
    data = request.get_json(force=True) or {}
    if not data.get("name"):
        return jsonify({"error": "Lab name is required"}), 400
    lab_id = db.create_lab(
        name=data.get("name", "").strip(),
        contact_name=data.get("contact_name", "").strip(),
        email=data.get("email", "").strip(),
        phone=data.get("phone", "").strip(),
        address=data.get("address", "").strip(),
        owner_name=data.get("owner_name", "").strip(),
        owner_address=data.get("owner_address", "").strip(),
        owner_ssn=data.get("owner_ssn", "").strip(),
    )
    lab = db.get_lab(lab_id)
    lab.pop("owner_ssn", None)  # never echo this back to the browser
    return jsonify(lab), 201


@app.route("/api/proposals", methods=["POST"])
def api_create_proposal():
    data = request.get_json(force=True) or {}
    lab_token = data.get("lab_token")
    inputs = data.get("inputs", {})
    client = data.get("client", {})

    lab = db.get_lab_by_token(lab_token)
    if not lab:
        return jsonify({"error": "Missing or invalid lab session -- start from the calculator link again."}), 400
    if not client.get("practice_name"):
        return jsonify({"error": "Client practice name is required"}), 400

    # Lab-side cost/financing terms are admin-configured, not client input --
    # always pull the authoritative values server-side rather than trust
    # whatever the browser sent for them.
    settings = db.get_settings()
    inputs["equipment_cost"] = settings["equipment_cost"]
    inputs["lab_down_payment"] = settings["lab_down_payment"]
    inputs["lab_apr"] = settings["lab_apr"]
    inputs["lab_term"] = settings["lab_term"]
    inputs["round_to"] = settings["round_to"]

    results = calc.compute(inputs)  # recompute server-side, never trust the client's numbers
    proposal_id = db.create_proposal(lab["id"], client, inputs, results)
    proposal = db.get_proposal(proposal_id)
    return jsonify({
        "token": proposal["token"],
        "lab_token": lab["access_token"],
        "proposal_url": url_for("view_proposal", token=proposal["token"]),
    }), 201


@app.route("/api/proposals/<token>", methods=["PUT"])
def api_update_proposal(token):
    """Update an existing proposal in place -- same link, corrected numbers --
    instead of spinning off a brand-new one."""
    p = db.get_proposal_by_token(token)
    if not p:
        return jsonify({"error": "Proposal not found"}), 404

    data = request.get_json(force=True) or {}
    inputs = data.get("inputs", {})
    client = data.get("client", {})
    if not client.get("practice_name"):
        return jsonify({"error": "Client practice name is required"}), 400

    # Same rule as creating a proposal: lab-side cost/financing terms always
    # come from the current admin settings, never from the browser.
    settings = db.get_settings()
    inputs["equipment_cost"] = settings["equipment_cost"]
    inputs["lab_down_payment"] = settings["lab_down_payment"]
    inputs["lab_apr"] = settings["lab_apr"]
    inputs["lab_term"] = settings["lab_term"]
    inputs["round_to"] = settings["round_to"]

    results = calc.compute(inputs)
    db.update_proposal(p["id"], client, inputs, results)
    return jsonify({
        "token": token,
        "proposal_url": url_for("view_proposal", token=token),
    })


# ---------------------------------------------------------------------------
# A lab's own view of its own work. The access token in the URL *is* the
# credential -- there's no separate login, but nothing here is guessable or
# enumerable, and it never lists or links to any other lab's data.
# ---------------------------------------------------------------------------
@app.route("/lab/<token>")
def lab_dashboard(token):
    lab = db.get_lab_by_token(token)
    if not lab:
        abort(404)
    proposals = db.list_proposals(lab["id"])
    return render_template("lab_dashboard.html", lab=lab, proposals=proposals)


# ---------------------------------------------------------------------------
# A single proposal and its two agreements, reachable only by their own
# unguessable token -- this is the link a lab bookmarks or emails to a
# doctor. No sequential IDs are exposed, so one proposal's link can't be
# used to find another lab's.
# ---------------------------------------------------------------------------
def _get_proposal_and_lab_or_404(token):
    p = db.get_proposal_by_token(token)
    if not p:
        abort(404)
    lab = db.get_lab(p["lab_id"])
    return p, lab


@app.route("/p/<token>")
def view_proposal(token):
    p, lab = _get_proposal_and_lab_or_404(token)
    return render_template("proposal.html", p=p, lab=lab)


@app.route("/p/<token>/agreement")
def view_agreement(token):
    p, lab = _get_proposal_and_lab_or_404(token)
    return render_template("agreement.html", p=p, lab=lab)


@app.route("/p/<token>/lab-agreement")
def view_lab_agreement(token):
    p, lab = _get_proposal_and_lab_or_404(token)
    return render_template("lab_agreement.html", p=p, lab=lab, supplier=config.SUPPLIER)


@app.route("/p/<token>/send-email", methods=["POST"])
def send_proposal_email(token):
    p, lab = _get_proposal_and_lab_or_404(token)
    data = request.get_json(force=True) or {}
    raw = (data.get("email") or "").strip()
    if not raw:
        return jsonify({"error": "Enter at least one email address."}), 400
    to_addrs = [a.strip() for a in raw.split(",") if a.strip()]

    proposal_url = url_for("view_proposal", token=token, _external=True)
    agreement_url = url_for("view_agreement", token=token, _external=True)
    lab_agreement_url = url_for("view_lab_agreement", token=token, _external=True)

    html_body = render_template(
        "email_proposal.html", p=p, lab=lab,
        proposal_url=proposal_url, agreement_url=agreement_url, lab_agreement_url=lab_agreement_url,
    )
    text_body = (
        f"Scanner lease proposal for {p['client_practice_name']} from {lab['name']}\n\n"
        f"Monthly Lease Payment: {usd_filter(p['results']['doctor']['monthly_payment'])}\n\n"
        f"Full proposal: {proposal_url}\n"
        f"Lease agreement: {agreement_url}\n"
        f"Equipment lease agreement: {lab_agreement_url}\n"
    )

    try:
        mailer.send_proposal_email(
            to_addrs,
            subject=f"Scanner lease proposal -- {p['client_practice_name']}",
            html_body=html_body,
            text_body=text_body,
        )
    except mailer.MailerNotConfigured as e:
        return jsonify({"error": str(e)}), 503
    except mailer.MailerError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": f"Could not send email: {e}"}), 502

    return jsonify({"ok": True})


@app.route("/p/<token>/status", methods=["POST"])
def set_status(token):
    p, _lab = _get_proposal_and_lab_or_404(token)
    status = (request.get_json(force=True) or {}).get("status", "draft")
    db.update_status(p["id"], status)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Admin -- the only place that can see every lab and every proposal.
# Gated by a single shared password (set ADMIN_PASSWORD as an env var).
# ---------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == config.ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        error = "Wrong password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    lab_id = request.args.get("lab_id", type=int)
    proposals = db.list_proposals(lab_id)
    labs = db.list_labs()
    return render_template("admin.html", proposals=proposals, labs=labs, selected_lab_id=lab_id)


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    saved = False
    if request.method == "POST":
        data = {
            "c_scanner": float(request.form.get("c_scanner", 0) or 0),
            "c_pc": float(request.form.get("c_pc", 0) or 0),
            "c_cart": float(request.form.get("c_cart", 0) or 0),
            "c_ship": float(request.form.get("c_ship", 0) or 0),
            "c_train": float(request.form.get("c_train", 0) or 0),
            "c_markup": float(request.form.get("c_markup", 0) or 0),
            "lab_down_payment": float(request.form.get("lab_down_payment", 0) or 0),
            "lab_apr": float(request.form.get("lab_apr", 0) or 0) / 100,
            "lab_term": int(request.form.get("lab_term", 36) or 36),
            "round_to": float(request.form.get("round_to", 5) or 5),
        }
        db.update_settings(data)
        saved = True
    settings = db.get_settings()
    lab_monthly_payment = calc.pmt(settings["lab_apr"], settings["lab_term"], settings["lab_financed"])
    return render_template("admin_settings.html", settings=settings, lab_monthly_payment=lab_monthly_payment, saved=saved)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
