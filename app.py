"""Change Management Hub — Main Application"""

import os
import json
from datetime import datetime, timezone

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_from_directory, abort, session as flask_session)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, ProjectDocument, Statistic, AudienceSegment
from models import Communication, Narrative, CorporateIdentity
from utils.ai_utils import interpret_statistics, generate_communication, generate_narrative
from utils.document_gen import generate_word_doc, generate_powerpoint
from utils.analytics import parse_stat_file, compute_summary_stats

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'csv', 'json', 'txt', 'png', 'jpg', 'jpeg', 'gif', 'svg'
}


# ---------------------------------------------------------------------------
# Jinja filters
# ---------------------------------------------------------------------------
import json as _json


@app.template_filter('from_json')
def from_json_filter(value):
    """Parse JSON string in Jinja templates."""
    if not value:
        return {}
    try:
        return _json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_brand():
    """Get brand settings from DB or fall back to config defaults."""
    identity = CorporateIdentity.query.first()
    if identity:
        return {
            'brand_name': identity.brand_name,
            'primary_colour': identity.primary_colour,
            'secondary_colour': identity.secondary_colour,
            'accent_colour': identity.accent_colour,
            'font_primary': identity.font_primary,
            'font_heading': identity.font_heading,
            'footer_text': identity.footer_text,
            'logo_path': identity.logo_path,
        }
    return Config.BRAND


def get_dashboard_stats():
    """Compute dashboard-level stats across the system."""
    total_docs = ProjectDocument.query.filter_by(is_active=True).count()
    total_stats = Statistic.query.filter_by(is_active=True).count()
    total_audiences = AudienceSegment.query.count()
    total_comms = Communication.query.count()
    total_narratives = Narrative.query.count()
    recent_docs = ProjectDocument.query.filter_by(is_active=True)\
        .order_by(ProjectDocument.uploaded_at.desc()).limit(5).all()
    recent_stats = Statistic.query.filter_by(is_active=True)\
        .order_by(Statistic.uploaded_at.desc()).limit(3).all()
    return {
        'total_documents': total_docs,
        'total_statistics': total_stats,
        'total_audiences': total_audiences,
        'total_communications': total_comms,
        'total_narratives': total_narratives,
        'recent_documents': recent_docs,
        'recent_statistics': recent_stats,
    }


# ---------------------------------------------------------------------------
# Routes — Auth
# ---------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Welcome back, ' + user.username, 'success')
            return redirect(url_for('index'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html', brand=get_brand())


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Routes — Dashboard
# ---------------------------------------------------------------------------
@app.route('/')
@login_required
def index():
    stats = get_dashboard_stats()
    return render_template('index.html', brand=get_brand(), stats=stats)


@app.route('/api/dashboard/data')
@login_required
def dashboard_data():
    """JSON endpoint for dashboard charts."""
    stats_data = []

    # Gather statistics with chart configs
    all_stats = Statistic.query.filter_by(is_active=True).order_by(Statistic.uploaded_at.desc()).all()
    for s in all_stats:
        chart = {}
        if s.chart_config:
            try:
                chart = json.loads(s.chart_config)
            except (json.JSONDecodeError, TypeError):
                pass
        stats_data.append({
            'id': s.id,
            'title': s.title,
            'period': s.period,
            'data_summary': s.data_summary,
            'chart_config': chart,
            'uploaded_at': s.uploaded_at.isoformat() if s.uploaded_at else '',
        })

    # Monthly communication count (simple aggregation)
    comms_by_month = {}
    for c in Communication.query.all():
        if c.generated_at:
            key = c.generated_at.strftime('%b %Y')
            comms_by_month[key] = comms_by_month.get(key, 0) + 1

    return jsonify({
        'statistics': stats_data,
        'comms_by_month': comms_by_month,
        'doc_count': ProjectDocument.query.filter_by(is_active=True).count(),
        'audience_count': AudienceSegment.query.count(),
        'comm_count': Communication.query.count(),
    })


# ---------------------------------------------------------------------------
# Routes — Document Management
# ---------------------------------------------------------------------------
@app.route('/documents')
@login_required
def documents():
    category = request.args.get('category', '')
    query = ProjectDocument.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)
    docs = query.order_by(ProjectDocument.updated_at.desc()).all()
    categories = [r[0] for r in db.session.query(ProjectDocument.category).distinct().all() if r[0]]
    return render_template('documents.html', brand=get_brand(), docs=docs, categories=categories)


@app.route('/documents/upload', methods=['POST'])
@login_required
def upload_document():
    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'General').strip()
    description = request.form.get('description', '').strip()
    file = request.files.get('file')

    if not title or not file:
        flash('Title and file are required.', 'danger')
        return redirect(url_for('documents'))

    if not allowed_file(file.filename):
        flash('File type not allowed.', 'danger')
        return redirect(url_for('documents'))

    filename = secure_filename(file.filename)
    # Prefix with timestamp to avoid collisions
    unique_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(filepath)
    file_size = os.path.getsize(filepath)

    doc = ProjectDocument(
        title=title,
        category=category,
        description=description,
        filename=filename,
        filepath=unique_name,
        file_size=file_size,
        file_type=filename.rsplit('.', 1)[-1].lower() if '.' in filename else '',
        uploaded_by=current_user.id,
    )
    db.session.add(doc)
    db.session.commit()
    flash(f'Document "{title}" uploaded successfully.', 'success')
    return redirect(url_for('documents'))


@app.route('/documents/<int:doc_id>/update', methods=['POST'])
@login_required
def update_document(doc_id):
    doc = db.session.get(ProjectDocument, doc_id) or abort(404)
    doc.title = request.form.get('title', doc.title).strip()
    doc.category = request.form.get('category', doc.category).strip()
    doc.description = request.form.get('description', doc.description).strip()

    # Optional replacement file
    file = request.files.get('file')
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(filepath)

        # Remove old file
        old_path = os.path.join(app.config['UPLOAD_FOLDER'], doc.filepath)
        if os.path.exists(old_path):
            os.remove(old_path)

        doc.filename = filename
        doc.filepath = unique_name
        doc.file_size = os.path.getsize(filepath)
        doc.file_type = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    db.session.commit()
    flash(f'Document "{doc.title}" updated.', 'success')
    return redirect(url_for('documents'))


@app.route('/documents/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_document(doc_id):
    doc = db.session.get(ProjectDocument, doc_id) or abort(404)
    # Soft delete
    doc.is_active = False
    db.session.commit()
    flash(f'Document "{doc.title}" removed.', 'info')
    return redirect(url_for('documents'))


@app.route('/documents/<int:doc_id>/view')
@login_required
def view_document(doc_id):
    doc = db.session.get(ProjectDocument, doc_id) or abort(404)
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        doc.filepath,
        download_name=doc.filename
    )


# ---------------------------------------------------------------------------
# Routes — Statistics & Analytics
# ---------------------------------------------------------------------------
@app.route('/statistics')
@login_required
def statistics():
    stats_list = Statistic.query.filter_by(is_active=True)\
        .order_by(Statistic.uploaded_at.desc()).all()
    dash_stats = get_dashboard_stats()
    return render_template('statistics.html', brand=get_brand(), stats_list=stats_list, stats=dash_stats)


@app.route('/statistics/upload', methods=['POST'])
@login_required
def upload_statistics():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    source = request.form.get('source', '').strip()
    period = request.form.get('period', '').strip()
    file = request.files.get('file')

    if not title or not file:
        flash('Title and file are required.', 'danger')
        return redirect(url_for('statistics'))

    if not allowed_file(file.filename):
        flash('File type not allowed.', 'danger')
        return redirect(url_for('statistics'))

    filename = secure_filename(file.filename)
    unique_name = f"stat_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(filepath)

    # Parse the file
    parsed = parse_stat_file(filepath)

    # AI interpretation
    raw_text = parsed.get('raw_text', '')
    if raw_text:
        ai_result = interpret_statistics(raw_text, title=title)
    else:
        ai_result = {}

    # Compute basic stats
    summary = compute_summary_stats(parsed)

    stat = Statistic(
        title=title,
        description=description,
        source=source,
        period=period,
        filename=filename,
        filepath=unique_name,
        data_summary=json.dumps({
            'ai': ai_result,
            'basic': summary,
            'parsed_headers': parsed.get('headers', []),
            'parsed_rows': len(parsed.get('rows', [])),
        }),
        chart_config=json.dumps({
            'type': ai_result.get('chart_type', 'bar'),
            'labels': ai_result.get('chart_labels', []),
            'values': ai_result.get('chart_values', []),
            'label': ai_result.get('chart_label', title),
            'insights': ai_result.get('insights', []),
            'recommendations': ai_result.get('recommendations', []),
            'kpi_cards': ai_result.get('kpi_cards', []),
        }),
        uploaded_by=current_user.id,
    )
    db.session.add(stat)
    db.session.commit()
    flash(f'Statistics "{title}" uploaded and analysed.', 'success')
    return redirect(url_for('statistics'))


@app.route('/statistics/<int:stat_id>/delete', methods=['POST'])
@login_required
def delete_statistic(stat_id):
    stat = db.session.get(Statistic, stat_id) or abort(404)
    stat.is_active = False
    db.session.commit()
    flash('Statistics removed.', 'info')
    return redirect(url_for('statistics'))


@app.route('/statistics/<int:stat_id>/reanalyse', methods=['POST'])
@login_required
def reanalyse_statistic(stat_id):
    """Re-run AI analysis on an existing statistic."""
    stat = db.session.get(Statistic, stat_id) or abort(404)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], stat.filepath)
    if not os.path.exists(filepath):
        flash('Source file not found.', 'danger')
        return redirect(url_for('statistics'))

    parsed = parse_stat_file(filepath)
    raw_text = parsed.get('raw_text', '')
    if raw_text:
        ai_result = interpret_statistics(raw_text, title=stat.title)
    else:
        ai_result = {}

    stat.data_summary = json.dumps({
        'ai': ai_result,
        'basic': compute_summary_stats(parsed),
        'parsed_headers': parsed.get('headers', []),
        'parsed_rows': len(parsed.get('rows', [])),
    })
    stat.chart_config = json.dumps({
        'type': ai_result.get('chart_type', 'bar'),
        'labels': ai_result.get('chart_labels', []),
        'values': ai_result.get('chart_values', []),
        'label': ai_result.get('chart_label', stat.title),
        'insights': ai_result.get('insights', []),
        'recommendations': ai_result.get('recommendations', []),
        'kpi_cards': ai_result.get('kpi_cards', []),
    })
    db.session.commit()
    flash('Statistics re-analysed.', 'success')
    return redirect(url_for('statistics'))


@app.route('/statistics/<int:stat_id>/data')
@login_required
def statistic_data(stat_id):
    """Return parsed data and chart config as JSON."""
    stat = db.session.get(Statistic, stat_id) or abort(404)
    chart = {}
    summary = {}
    if stat.chart_config:
        try:
            chart = json.loads(stat.chart_config)
        except (json.JSONDecodeError, TypeError):
            pass
    if stat.data_summary:
        try:
            summary = json.loads(stat.data_summary)
        except (json.JSONDecodeError, TypeError):
            pass

    return jsonify({
        'id': stat.id,
        'title': stat.title,
        'description': stat.description,
        'source': stat.source,
        'period': stat.period,
        'chart': chart,
        'summary': summary,
    })


# ---------------------------------------------------------------------------
# Routes — Audience Segmentation
# ---------------------------------------------------------------------------
@app.route('/audiences')
@login_required
def audiences():
    segments = AudienceSegment.query.order_by(AudienceSegment.name).all()
    return render_template('audiences.html', brand=get_brand(), segments=segments)


@app.route('/audiences/create', methods=['POST'])
@login_required
def create_audience():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Audience name is required.', 'danger')
        return redirect(url_for('audiences'))

    segment = AudienceSegment(
        name=name,
        description=request.form.get('description', '').strip(),
        attributes=request.form.get('attributes', '').strip(),
        communication_prefs=request.form.get('communication_prefs', '').strip(),
        stakeholder_level=request.form.get('stakeholder_level', '').strip(),
        created_by=current_user.id,
    )
    db.session.add(segment)
    db.session.commit()
    flash(f'Audience segment "{name}" created.', 'success')
    return redirect(url_for('audiences'))


@app.route('/audiences/<int:aud_id>/update', methods=['POST'])
@login_required
def update_audience(aud_id):
    seg = db.session.get(AudienceSegment, aud_id) or abort(404)
    seg.name = request.form.get('name', seg.name).strip()
    seg.description = request.form.get('description', seg.description).strip()
    seg.attributes = request.form.get('attributes', seg.attributes).strip()
    seg.communication_prefs = request.form.get('communication_prefs', seg.communication_prefs).strip()
    seg.stakeholder_level = request.form.get('stakeholder_level', seg.stakeholder_level).strip()
    db.session.commit()
    flash(f'"{seg.name}" updated.', 'success')
    return redirect(url_for('audiences'))


@app.route('/audiences/<int:aud_id>/delete', methods=['POST'])
@login_required
def delete_audience(aud_id):
    seg = db.session.get(AudienceSegment, aud_id) or abort(404)
    db.session.delete(seg)
    db.session.commit()
    flash('Audience segment removed.', 'info')
    return redirect(url_for('audiences'))


# ---------------------------------------------------------------------------
# Routes — Communications Generation
# ---------------------------------------------------------------------------
@app.route('/communications')
@login_required
def communications():
    comms = Communication.query.order_by(Communication.generated_at.desc()).all()
    audiences = AudienceSegment.query.order_by(AudienceSegment.name).all()
    return render_template('communications.html', brand=get_brand(),
                           comms=comms, audiences=audiences)


@app.route('/communications/generate', methods=['POST'])
@login_required
def generate_comm():
    title = request.form.get('title', '').strip()
    comm_type = request.form.get('comm_type', 'email').strip()
    audience_id = request.form.get('audience_id', type=int)
    tone = request.form.get('tone', 'professional').strip()
    purpose = request.form.get('purpose', '').strip()
    key_messages_raw = request.form.get('key_messages', '').strip()
    generate_docx = request.form.get('generate_docx') == 'on'
    generate_pptx = request.form.get('generate_pptx') == 'on'

    if not title or not purpose:
        flash('Title and purpose are required.', 'danger')
        return redirect(url_for('communications'))

    # Get audience info
    audience_info = {'name': 'Stakeholders', 'description': '', 'attributes': '', 'communication_prefs': ''}
    audience_name = 'Stakeholders'
    if audience_id:
        seg = db.session.get(AudienceSegment, audience_id)
        if seg:
            audience_info = {
                'name': seg.name,
                'description': seg.description,
                'attributes': seg.attributes,
                'communication_prefs': seg.communication_prefs,
            }
            audience_name = seg.name

    key_msgs_list = [m.strip() for m in key_messages_raw.split('\n') if m.strip()] if key_messages_raw else None

    # Generate content via AI
    brand = get_brand()
    result = generate_communication(audience_info, purpose, tone=tone,
                                    key_messages=key_msgs_list, brand=brand)

    # Build full body with all parts
    full_body = f"{result.get('greeting', '')}\n\n{result.get('body', '')}\n\n{result.get('call_to_action', '')}\n\n{result.get('closing', '')}"

    # Generate email HTML
    email_html = _build_email_html(result, brand, audience_name)

    comm = Communication(
        title=title,
        comm_type=comm_type,
        audience_id=audience_id,
        audience_name=audience_name,
        content_text=json.dumps(result),
        tone=tone,
        purpose=purpose,
        generated_by=current_user.id,
        status='draft',
        email_html=email_html,
    )

    # Generate Word doc
    if generate_docx:
        docx_name = f"comm_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.docx"
        docx_path = os.path.join(app.config['UPLOAD_FOLDER'], docx_name)
        generate_word_doc(result, brand, docx_path)
        comm.docx_path = docx_name

    # Generate PowerPoint
    if generate_pptx:
        pptx_name = f"comm_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.pptx"
        pptx_path = os.path.join(app.config['UPLOAD_FOLDER'], pptx_name)
        generate_powerpoint(result, brand, pptx_path)
        comm.pptx_path = pptx_name

    db.session.add(comm)
    db.session.commit()
    flash(f'Communication "{title}" generated for {audience_name}.', 'success')
    return redirect(url_for('communications'))


def _build_email_html(result, brand, audience_name):
    """Build an email-ready HTML snippet."""
    subject = result.get('subject', 'Communication')
    greeting = result.get('greeting', '')
    body = result.get('body', '')
    cta = result.get('call_to_action', '')
    closing = result.get('closing', '')

    navy = '#001D38'
    teal = '#00B398'
    gold = '#C8A064'
    muted = '#6c7a8a'

    body_paragraphs = ''.join(
        '<p style="color:' + navy + ';font-size:14px;line-height:1.6;">' + p.strip() + '</p>'
        for p in body.split('\n\n') if p.strip()
    )

    closing_lines = ''.join(
        '<p style="color:' + navy + ';font-size:14px;margin:2px 0;">' + l.strip() + '</p>'
        for l in closing.split('\n') if l.strip()
    )

    return '''<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#eef1f4;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:30px 0;">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:6px;overflow:hidden;box-shadow:0 2px 16px rgba(0,29,56,0.08);">
<tr><td style="background:''' + navy + ''';padding:20px 30px;border-bottom:3px solid ''' + gold + ''';">
<table width="100%"><tr>
<td><span style="color:''' + gold + ''';font-size:12px;font-weight:bold;letter-spacing:1px;">IMPACT PROGRAMME</span></td>
<td style="text-align:right;"><span style="color:''' + teal + ''';font-size:10px;">CHANGE MANAGEMENT</span></td>
</tr></table>
</td></tr>
<tr><td style="padding:30px;">
<h1 style="color:''' + navy + ''';font-size:20px;margin:0 0 16px 0;">''' + subject + '''</h1>
<p style="color:''' + navy + ''';font-size:14px;margin:0 0 16px 0;"><strong>''' + greeting + '''</strong></p>''' + body_paragraphs + '''
<p style="color:''' + teal + ''';font-size:14px;font-weight:bold;margin:16px 0 10px 0;">''' + cta + '''</p>''' + closing_lines + '''
</td></tr>
<tr><td style="background:''' + navy + ''';padding:14px 30px;text-align:center;">
<span style="color:''' + muted + ''';font-size:10px;">Gold Fields · IMPACT Programme · Confidential</span>
</td></tr>
</table>
</td></tr></table>
</body></html>'''


@app.route('/communications/<int:comm_id>/email')
@login_required
def view_email(comm_id):
    comm = db.session.get(Communication, comm_id) or abort(404)
    return render_template('email_preview.html', brand=get_brand(), comm=comm)


@app.route('/communications/<int:comm_id>/download/<file_type>')
@login_required
def download_comm(comm_id, file_type):
    comm = db.session.get(Communication, comm_id) or abort(404)
    if file_type == 'docx' and comm.docx_path:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], comm.docx_path,
            download_name=f"{comm.title.replace(' ', '_')}.docx"
        )
    elif file_type == 'pptx' and comm.pptx_path:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], comm.pptx_path,
            download_name=f"{comm.title.replace(' ', '_')}.pptx"
        )
    elif file_type == 'html' and comm.email_html:
        return comm.email_html, 200, {'Content-Type': 'text/html; charset=utf-8'}
    flash('File not found.', 'danger')
    return redirect(url_for('communications'))


@app.route('/communications/<int:comm_id>/delete', methods=['POST'])
@login_required
def delete_communication(comm_id):
    comm = db.session.get(Communication, comm_id) or abort(404)
    # Clean up files
    for attr in ['docx_path', 'pptx_path']:
        path = getattr(comm, attr, '')
        if path:
            full = os.path.join(app.config['UPLOAD_FOLDER'], path)
            if os.path.exists(full):
                os.remove(full)
    db.session.delete(comm)
    db.session.commit()
    flash('Communication removed.', 'info')
    return redirect(url_for('communications'))


# ---------------------------------------------------------------------------
# Routes — Narrative & Messaging
# ---------------------------------------------------------------------------
@app.route('/narratives')
@login_required
def narratives():
    narratives_list = Narrative.query.order_by(Narrative.updated_at.desc()).all()
    audiences = AudienceSegment.query.order_by(AudienceSegment.name).all()
    return render_template('narratives.html', brand=get_brand(),
                           narratives=narratives_list, audiences=audiences)


@app.route('/narratives/create', methods=['POST'])
@login_required
def create_narrative():
    title = request.form.get('title', '').strip()
    narrative_type = request.form.get('narrative_type', 'change_story').strip()
    context = request.form.get('context', '').strip()
    audience_id = request.form.get('audience_id', type=int)

    if not title or not context:
        flash('Title and context are required.', 'danger')
        return redirect(url_for('narratives'))

    audience_info = None
    if audience_id:
        seg = db.session.get(AudienceSegment, audience_id)
        if seg:
            audience_info = {
                'name': seg.name,
                'description': seg.description,
                'attributes': seg.attributes,
                'communication_prefs': seg.communication_prefs,
            }

    brand = get_brand()
    result = generate_narrative(narrative_type, context, audience_info=audience_info, brand=brand)

    narrative = Narrative(
        title=title,
        narrative_type=narrative_type,
        content=result.get('content', ''),
        key_messages=json.dumps({
            'key_messages': result.get('key_messages', []),
            'talking_points': result.get('talking_points', []),
            'recommended_vehicles': result.get('recommended_vehicles', []),
        }),
        audience_id=audience_id,
        created_by=current_user.id,
    )
    db.session.add(narrative)
    db.session.commit()
    flash(f'Narrative "{title}" created.', 'success')
    return redirect(url_for('narratives'))


@app.route('/narratives/<int:narr_id>/update', methods=['POST'])
@login_required
def update_narrative(narr_id):
    narr = db.session.get(Narrative, narr_id) or abort(404)
    narr.title = request.form.get('title', narr.title).strip()
    narr.content = request.form.get('content', narr.content)
    narr.key_messages = request.form.get('key_messages', narr.key_messages)
    narr.narrative_type = request.form.get('narrative_type', narr.narrative_type)
    narr.version = (narr.version or 0) + 1
    db.session.commit()
    flash(f'"{narr.title}" updated (v{narr.version}).', 'success')
    return redirect(url_for('narratives'))


@app.route('/narratives/<int:narr_id>/delete', methods=['POST'])
@login_required
def delete_narrative(narr_id):
    narr = db.session.get(Narrative, narr_id) or abort(404)
    db.session.delete(narr)
    db.session.commit()
    flash('Narrative removed.', 'info')
    return redirect(url_for('narratives'))


# ---------------------------------------------------------------------------
# Routes — Corporate Identity
# ---------------------------------------------------------------------------
@app.route('/identity')
@login_required
def identity():
    identity_data = CorporateIdentity.query.first()
    return render_template('identity.html', brand=get_brand(), identity=identity_data)


@app.route('/identity/update', methods=['POST'])
@login_required
def update_identity():
    identity_data = CorporateIdentity.query.first()
    if not identity_data:
        identity_data = CorporateIdentity()
        db.session.add(identity_data)

    identity_data.brand_name = request.form.get('brand_name', identity_data.brand_name).strip()
    identity_data.primary_colour = request.form.get('primary_colour', identity_data.primary_colour).strip()
    identity_data.secondary_colour = request.form.get('secondary_colour', identity_data.secondary_colour).strip()
    identity_data.accent_colour = request.form.get('accent_colour', identity_data.accent_colour).strip()
    identity_data.font_primary = request.form.get('font_primary', identity_data.font_primary).strip()
    identity_data.font_heading = request.form.get('font_heading', identity_data.font_heading).strip()
    identity_data.footer_text = request.form.get('footer_text', identity_data.footer_text).strip()

    # Handle logo upload
    logo = request.files.get('logo')
    if logo and allowed_file(logo.filename):
        filename = secure_filename(logo.filename)
        logo_name = f"logo_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{filename}"
        logo_path = os.path.join(app.config['LOGO_FOLDER'], logo_name)
        logo.save(logo_path)
        identity_data.logo_path = logo_name

    db.session.commit()
    flash('Corporate identity updated.', 'success')
    return redirect(url_for('identity'))


# ---------------------------------------------------------------------------
# Serve uploaded files
# ---------------------------------------------------------------------------
@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/logos/<filename>')
@login_required
def logo_file(filename):
    return send_from_directory(app.config['LOGO_FOLDER'], filename)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template('base.html', brand=get_brand(),
                           error_code=404, error_msg='Page not found'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('base.html', brand=get_brand(),
                           error_code=500, error_msg='Server error'), 500


# ---------------------------------------------------------------------------
# Startup — create DB and default users
# ---------------------------------------------------------------------------
def init_db():
    with app.app_context():
        db.create_all()

        # Create default admin user
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@cmhub.local', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)

        # Create default change manager
        if not User.query.filter_by(username='manager').first():
            mgr = User(username='manager', email='manager@cmhub.local', role='change_manager')
            mgr.set_password('manager123')
            db.session.add(mgr)

        # Seed default corporate identity
        if not CorporateIdentity.query.first():
            ci = CorporateIdentity()
            db.session.add(ci)

        # Seed sample audience segments
        if not AudienceSegment.query.first():
            segments = [
                AudienceSegment(
                    name='Executive Leadership',
                    description='C-suite and senior VPs who sponsor the change',
                    attributes='Decision-makers, strategic view, limited time, need high-level impact data',
                    communication_prefs='Briefing decks, email summaries, quarterly reviews',
                    stakeholder_level='Executive',
                ),
                AudienceSegment(
                    name='Line Managers',
                    description='Direct managers of teams affected by the change',
                    attributes='Operational focus, need practical guidance, manage team adoption',
                    communication_prefs='Team meetings toolkits, email updates, 1-pagers',
                    stakeholder_level='Management',
                ),
                AudienceSegment(
                    name='Frontline Teams',
                    description='Employees directly impacted by day-to-day changes',
                    attributes='Want to know WIIFM (what\'s in it for me), practical impact on daily work',
                    communication_prefs='Town halls, team huddles, simple infographics',
                    stakeholder_level='Frontline',
                ),
                AudienceSegment(
                    name='Project Team',
                    description='Change network and implementation team members',
                    attributes='Detail-oriented, need timelines, risks, and action items',
                    communication_prefs='Project dashboards, weekly standups, collaboration tools',
                    stakeholder_level='Operational',
                ),
            ]
            db.session.add_all(segments)

        db.session.commit()


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5055))
    app.run(host='0.0.0.0', port=port, debug=True)
else:
    # Serverless (Vercel) — initialize DB on cold start
    with app.app_context():
        db.create_all()
        # Only seed if tables are empty
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@cmhub.local', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
        if not User.query.filter_by(username='manager').first():
            mgr = User(username='manager', email='manager@cmhub.local', role='change_manager')
            mgr.set_password('manager123')
            db.session.add(mgr)
        if not CorporateIdentity.query.first():
            ci = CorporateIdentity()
            db.session.add(ci)
        if not AudienceSegment.query.first():
            segments = [
                AudienceSegment(name='Executive Leadership', description='C-suite and senior VPs',
                    attributes='Decision-makers, strategic view, limited time',
                    communication_prefs='Briefing decks, email summaries',
                    stakeholder_level='Executive'),
                AudienceSegment(name='Line Managers', description='Direct managers of teams',
                    attributes='Operational focus, need practical guidance',
                    communication_prefs='Team meetings toolkits, email updates',
                    stakeholder_level='Management'),
                AudienceSegment(name='Frontline Teams', description='Employees directly impacted',
                    attributes='Want to know WIIFM, practical impact on daily work',
                    communication_prefs='Town halls, team huddles, simple infographics',
                    stakeholder_level='Frontline'),
                AudienceSegment(name='Project Team', description='Change network and implementation team',
                    attributes='Detail-oriented, need timelines and action items',
                    communication_prefs='Project dashboards, weekly standups',
                    stakeholder_level='Operational'),
            ]
            db.session.add_all(segments)
        db.session.commit()
