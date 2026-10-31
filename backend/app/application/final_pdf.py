"""Generate a read-only PDF from an authorised, already-saved final snapshot."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import RLock
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether

FONT='CampMateSansSC'
FONT_PATH=Path(__file__).resolve().parents[1]/'assets/fonts/CampMateSansSC-Regular.ttf'
_FONT_LOCK=RLock()
LABELS={'LOGISTICS':'Equipment and costs','SAFETY':'Safety','WEATHER':'Weather','FIRE':'Fire use','ROAD':'Road','RESTRICTION':'Campsite rules',
    'CAMPSITE':'Campsite fee','TRANSPORT':'Transport','FOOD':'Food','WATER':'Drinking water','ADDITIONAL_GEAR':'Equipment gaps',
    'APPROVE':'Approve','REQUEST_REVISION':'Request revision','REJECT':'Reject','PASSED':'Pass','REVIEW':'Human judgement',
    'LOW':'Low','MEDIUM':'Medium','HIGH':'High','UNKNOWN':'Unknown','AVAILABLE':'Information available','ACTIVITY':'Activity','CAMP':'Overnight','TRAVEL':'Transport'}


def render_final_pdf(saved,*,is_current):
    if saved.get('status')!='FINALISED' or saved.get('review') and saved['review'].get('decision')!='APPROVE':
        raise ValueError('Only saved final records can be exported')
    with _FONT_LOCK:
        if FONT not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(FONT,str(FONT_PATH)))
    style=ParagraphStyle('body',fontName=FONT,fontSize=10,leading=16,wordWrap='CJK',spaceAfter=6,alignment=TA_LEFT)
    heading=ParagraphStyle('heading',parent=style,fontSize=14,leading=20,spaceBefore=12,spaceAfter=8,keepWithNext=True,textColor=colors.HexColor('#214b3c'))
    title=ParagraphStyle('title',parent=heading,fontSize=20,leading=26)
    story=[]
    unsupported=set()
    coverage=pdfmetrics.getFont(FONT).face.charToGlyph
    def text(value):
        original='Not recorded' if value is None else str(value)
        safe=[]
        for char in original:
            if char in '\n\r\t' or ord(char) in coverage:safe.append(char)
            else:unsupported.add(ord(char));safe.append('[U+'+format(ord(char),'04X')+']')
        return escape(''.join(safe)).replace('\n','<br/>')
    def p(value,chosen=style):return Paragraph(text(value),chosen)
    def add(value):story.append(p(value))
    def section(value):story.append(p(value,heading))
    def label(value):return LABELS.get(value,value or 'Not recorded')
    def money(value):return 'Undetermined' if value is None else 'AUD '+format(Decimal(str(value))/100,'.2f')
    def instant(value):
        if not value:return 'Not recorded'
        return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('Australia/Sydney')).strftime('%Y-%m-%d %H:%M')+' (Sydney time)'
    def table(headers,rows,widths):
        content=[[p(value) for value in headers],*[[p(value) for value in row] for row in rows]]
        t=Table(content,colWidths=[width*mm for width in widths],repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf2e7')),
            ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#d1d9cf')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([t,Spacer(1,8)])
    story.append(p('CampMate Saved final plan',title))
    add('Current final record' if is_current else 'Historical final record: this does not establish that the current plan passed checks or review.')
    context=saved['version_context'];confirmed=saved['confirmed_context'];req=confirmed['requirements'];content=saved['content']
    add('Version '+str(saved['version_number'])+' · Saved '+instant(saved['finalised_at']))
    add('Final record ID: '+saved['final_id']);add('Plan ID: '+context['plan_id']);add('Version ID: '+context['plan_version_id'])
    add('Run ID: '+context['run_id'])
    if any(ref.get('provenance',{}).get('demo_only') for ref in content.get('source_refs',[])):
        add('Contains demo / simulated information and suggestions. Does not confirm bookings, live access or actual trip safety.')
    section('Confirmed trip requirements')
    add(str(req.get('destination') or 'Not recorded')+' · '+str(req.get('start_date'))+' to '+str(req.get('end_date')))
    add('Group size: '+str(confirmed.get('profile_snapshot',{}).get('group_size') or 'Not recorded')+'; Budget: '+money(req.get('budget_cents')))
    for key,name in [('preferences','Preferences'),('mandatory_constraints','Required conditions')]:add(name+': '+', '.join(req.get(key,[])))
    section('Itinerary (all times suggested / pending confirmation)')
    for entry in content.get('itinerary_entries',[]):
        story.append(KeepTogether([p(label(entry['entry_kind'])+' · '+str(entry.get('campsite_id') or 'Not recorded'),heading),
            p(instant(entry['start_at'])+' to '+instant(entry['end_at'])),p(entry['description'])]))
    assessments={row['kind']:row['result'] for row in saved.get('assessments',[])}
    logistics=assessments.get('LOGISTICS',{});safety=assessments.get('SAFETY',{})
    section('Costs and budget (estimates)')
    add('Estimated total: '+money(logistics.get('total_cents'))+'; Known subtotal: '+money(logistics.get('known_subtotal_cents')))
    table(['Cost item','Quantity / unit','Unit price','Subtotal'],[[label(row['category'])+' / '+row['item_key'],str(row.get('quantity'))+' / '+row['unit'],money(row.get('unit_price_cents')),money(row.get('subtotal_cents'))] for row in logistics.get('cost_breakdown',[])],[65,35,34,34])
    for row in logistics.get('cost_breakdown',[]):
        if row.get('assumption'):add(row['item_key']+': '+row['assumption'])
    for value in logistics.get('assumptions',[]):add('Cost assumptions: '+value)
    section('Equipment checklist')
    table(['Equipment','Required quantity','Available','Shortfall'],[[row['item_key'],str(row.get('required_quantity'))+' / '+row['unit'],row.get('available_quantity'),row.get('missing_quantity')] for row in logistics.get('gear_checklist',[])],[65,35,34,34])
    section('Saved safety assessments and source dates')
    add('Assessment: '+label(safety.get('outcome'))+'; Risk: '+label(safety.get('risk_level'))+'; Confidence: '+label(safety.get('confidence')))
    for row in safety.get('evidence',[]):
        add(label(row['kind'])+' · '+label(row['status'])+' · Source date: '+str(row.get('source_date') or 'Not recorded'))
        add('Source coverage: '+str(row.get('valid_from') or 'Not recorded')+' to '+str(row.get('valid_to') or 'Not recorded'));add(row.get('summary'))
        for ref in row.get('source_refs',[]):add('Source: '+str(ref.get('provenance',{}).get('source_name','Not recorded'))+' / '+ref['record_id'])
    for name,key in [('Risk','hazards'),('Suggestions','recommended_actions'),('Restrictions','mandatory_blockers')]:
        for row in safety.get(key,[]):add(name+': '+(row.get('message','') if isinstance(row,dict) else row))
    section('Human review record')
    review=saved.get('review')
    if review:
        add('Decision: '+label(review['decision'])+'; Review records ID: '+review['review_id']);add('Reason: '+review['reason'])
        add('Review applies only to the saved version above, not subsequent revisions or new assessments.')
    else:add('No human review decision was recorded in this final snapshot.')
    if unsupported:add('Characters unavailable in the font are represented by their Unicode code. Original content remains in the saved web record.')
    buffer=BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=21*mm,leftMargin=21*mm,topMargin=18*mm,bottomMargin=20*mm,
        title='CampMate saved final plan',author='CampMate',invariant=1)
    def footer(canvas,document):
        canvas.saveState();canvas.setFont(FONT,9)
        canvas.drawString(21*mm,11*mm,'CampMate · Saved snapshot · '+saved['final_id'])
        canvas.drawRightString(189*mm,11*mm,str(document.page));canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()
