"""Founder history index; historical decisions grant no current operation."""
import json
from ..auth import require_role


def history(database,user,*,decision=None,offset=0,limit=30):
    require_role(user,'FOUNDER')
    condition=' AND json_extract(h.payload,\'$.decision\')=?' if decision else ''
    params=[decision] if decision else []
    # Reviews are linked through their immutable run and version, not a current pointer.
    base=''' FROM reviews h JOIN runs r ON r.id=h.run_id JOIN plans p ON p.id=r.plan_id
        JOIN versions v ON v.id=h.version_id JOIN users u ON u.id=p.owner_id
        WHERE p.deleted_at IS NULL AND NOT EXISTS(
            SELECT 1 FROM plan_series_members m JOIN trip_series s ON s.id=m.series_id
            WHERE m.plan_id=p.id AND s.deleted_at IS NOT NULL)'''+condition
    with database.transaction(write=False) as connection:
        total=connection.execute('SELECT COUNT(*)'+base,params).fetchone()[0]
        rows=connection.execute('''SELECT h.payload,h.created_at,p.id AS plan_id,r.id AS run_id,v.id AS plan_version_id,
            v.version_number,u.display_name AS owner_display_name,
            r.confirmed_context,p.active_run_id,p.current_version_id'''+base+' ORDER BY h.created_at DESC,h.rowid DESC LIMIT ? OFFSET ?',(*params,limit,offset)).fetchall()
        result=[]
        from .trip_series import plan_series_view
        for row in rows:
            review=json.loads(row['payload']);confirmed=json.loads(row['confirmed_context'])
            series=plan_series_view(connection,row['plan_id'])
            current=row['active_run_id']==row['run_id'] and row['current_version_id']==row['plan_version_id'] and (not series or series['is_current'])
            result.append({key:row[key] for key in ['plan_id','run_id','plan_version_id','version_number','owner_display_name','created_at']}|
                {'review_id':review['review_id'],'decision':review['decision'],'reason':review['reason'],'is_current_result':current,
                 'destination':confirmed['requirements'].get('destination'),'start_date':confirmed['requirements'].get('start_date')})
        return {'reviews':result,'total':total,'offset':offset,'limit':limit}
