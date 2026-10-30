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
LABELS={'LOGISTICS':'装备与费用','SAFETY':'安全','WEATHER':'天气','FIRE':'用火','ROAD':'道路','RESTRICTION':'营地规定',
    'CAMPSITE':'营地费','TRANSPORT':'交通','FOOD':'食物','WATER':'饮用水','ADDITIONAL_GEAR':'装备补缺',
    'APPROVE':'批准','REQUEST_REVISION':'要求修订','REJECT':'拒绝','PASSED':'通过','REVIEW':'人工判断',
    'LOW':'低','MEDIUM':'中','HIGH':'高','UNKNOWN':'未知','AVAILABLE':'资料可用','ACTIVITY':'活动','CAMP':'过夜','TRAVEL':'交通'}


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
        original='未记录' if value is None else str(value)
        safe=[]
        for char in original:
            if char in '\n\r\t' or ord(char) in coverage:safe.append(char)
            else:unsupported.add(ord(char));safe.append('[U+'+format(ord(char),'04X')+']')
        return escape(''.join(safe)).replace('\n','<br/>')
    def p(value,chosen=style):return Paragraph(text(value),chosen)
    def add(value):story.append(p(value))
    def section(value):story.append(p(value,heading))
    def label(value):return LABELS.get(value,value or '未记录')
    def money(value):return '未确定' if value is None else 'AUD '+format(Decimal(str(value))/100,'.2f')
    def instant(value):
        if not value:return '未记录'
        return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('Australia/Sydney')).strftime('%Y-%m-%d %H:%M')+'（悉尼时间）'
    def table(headers,rows,widths):
        content=[[p(value) for value in headers],*[[p(value) for value in row] for row in rows]]
        t=Table(content,colWidths=[width*mm for width in widths],repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf2e7')),
            ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#d1d9cf')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([t,Spacer(1,8)])
    story.append(p('CampMate 已保存的最终方案',title))
    add('当前最终记录' if is_current else '历史最终记录：不表示当前方案已通过检查或审核。')
    context=saved['version_context'];confirmed=saved['confirmed_context'];req=confirmed['requirements'];content=saved['content']
    add('版本 '+str(saved['version_number'])+' · 保存于 '+instant(saved['finalised_at']))
    add('最终记录 ID：'+saved['final_id']);add('方案 ID：'+context['plan_id']);add('版本 ID：'+context['plan_version_id'])
    add('运行 ID：'+context['run_id'])
    if any(ref.get('provenance',{}).get('demo_only') for ref in content.get('source_refs',[])):
        add('包含演示／模拟资料及建议，不代表已预订、实时开放或实际出行安全保证。')
    section('已确认的出行需求')
    add(str(req.get('destination') or '未记录')+' · '+str(req.get('start_date'))+' 至 '+str(req.get('end_date')))
    add('同行人数：'+str(confirmed.get('profile_snapshot',{}).get('group_size') or '未记录')+'；预算：'+money(req.get('budget_cents')))
    for key,name in [('preferences','偏好'),('mandatory_constraints','必须条件')]:add(name+'：'+'、'.join(req.get(key,[])))
    section('行程安排（所有时段均为建议／待确认）')
    for entry in content.get('itinerary_entries',[]):
        story.append(KeepTogether([p(label(entry['entry_kind'])+' · '+str(entry.get('campsite_id') or '未记录'),heading),
            p(instant(entry['start_at'])+' 至 '+instant(entry['end_at'])),p(entry['description'])]))
    assessments={row['kind']:row['result'] for row in saved.get('assessments',[])}
    logistics=assessments.get('LOGISTICS',{});safety=assessments.get('SAFETY',{})
    section('费用与预算（估算）')
    add('预计合计：'+money(logistics.get('total_cents'))+'；已知部分小计：'+money(logistics.get('known_subtotal_cents')))
    table(['费用项目','数量／单位','单价','小计'],[[label(row['category'])+' / '+row['item_key'],str(row.get('quantity'))+' / '+row['unit'],money(row.get('unit_price_cents')),money(row.get('subtotal_cents'))] for row in logistics.get('cost_breakdown',[])],[65,35,34,34])
    for row in logistics.get('cost_breakdown',[]):
        if row.get('assumption'):add(row['item_key']+'：'+row['assumption'])
    for value in logistics.get('assumptions',[]):add('费用假设：'+value)
    section('装备清单')
    table(['装备','所需数量','已具备','缺口'],[[row['item_key'],str(row.get('required_quantity'))+' / '+row['unit'],row.get('available_quantity'),row.get('missing_quantity')] for row in logistics.get('gear_checklist',[])],[65,35,34,34])
    section('已保存的安全评估与来源日期')
    add('评估：'+label(safety.get('outcome'))+'；风险：'+label(safety.get('risk_level'))+'；置信度：'+label(safety.get('confidence')))
    for row in safety.get('evidence',[]):
        add(label(row['kind'])+' · '+label(row['status'])+' · 来源日期：'+str(row.get('source_date') or '未记录'))
        add('资料适用期：'+str(row.get('valid_from') or '未记录')+' 至 '+str(row.get('valid_to') or '未记录'));add(row.get('summary'))
        for ref in row.get('source_refs',[]):add('来源：'+str(ref.get('provenance',{}).get('source_name','未记录'))+' / '+ref['record_id'])
    for name,key in [('风险','hazards'),('建议','recommended_actions'),('限制','mandatory_blockers')]:
        for row in safety.get(key,[]):add(name+'：'+(row.get('message','') if isinstance(row,dict) else row))
    section('人工审核记录')
    review=saved.get('review')
    if review:
        add('决定：'+label(review['decision'])+'；审核记录 ID：'+review['review_id']);add('理由：'+review['reason'])
        add('审核仅针对上述已保存版本，不授权后续修订或新评估。')
    else:add('此最终快照未记录人工审核决定。')
    if unsupported:add('字体未覆盖的字符使用 Unicode 编号表示；原始内容仍保留在已保存网页记录中。')
    buffer=BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=21*mm,leftMargin=21*mm,topMargin=18*mm,bottomMargin=20*mm,
        title='CampMate saved final plan',author='CampMate',invariant=1)
    def footer(canvas,document):
        canvas.saveState();canvas.setFont(FONT,9)
        canvas.drawString(21*mm,11*mm,'CampMate · 已保存快照 · '+saved['final_id'])
        canvas.drawRightString(189*mm,11*mm,str(document.page));canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()
