/* Optional local field view. Consumes existing state and event refreshes only. */
(function () {
    'use strict';
    function safe(value, limit) { return typeof value === 'string' ? value.slice(0, limit || 120) : ''; }
    function build(state, now, failed) {
        state = state || {};
        var epoch = state.snapshot_epoch, valid = typeof epoch === 'number' && Number.isFinite(epoch) && epoch > 0;
        var freshness = failed ? 'OFFLINE' : !valid || epoch > now + 5 ? 'UNKNOWN' : now - epoch > 10 ? 'STALE' : 'CURRENT';
        var mode = safe((state.mode || {}).current_mode).toLowerCase();
        if (['shield', 'portal', 'scapegoat'].indexOf(mode) < 0) mode = 'unknown';
        var epd = ((state.mode_runtime || {}).epd_state || {}), target = safe(epd.target_mode).toLowerCase();
        if (epd.mode !== 'switching' || ['shield','portal','scapegoat'].indexOf(target) < 0) target = '';
        var connection = state.connection || {}, monitoring = state.monitoring || {};
        return {freshness: freshness, epoch: valid ? epoch : null, mode: mode.toUpperCase(), target: target.toUpperCase(),
            wifi: safe(connection.wifi_state) || 'UNKNOWN', internet: safe(connection.internet_check) || 'UNKNOWN',
            portal: safe(connection.captive_portal) || 'UNKNOWN', nat: safe(connection.usb_nat) || 'UNKNOWN',
            sensor: safe(monitoring.suricata) || 'UNKNOWN', decoy: safe(monitoring.opencanary) || 'UNKNOWN',
            warning: safe((state.internal || {}).state_name) || 'UNKNOWN'};
    }
    if (typeof module !== 'undefined' && module.exports) module.exports = {build: build};
    if (typeof document === 'undefined') return;
    var root=document.getElementById('fieldOverview'); if (!root) return;
    var latest={}, failed=false, timer=null, events=[], request=null;
    function put(id,value) { document.getElementById(id).textContent=value; }
    function render() {
        var model=build(latest,Date.now()/1000,failed); root.dataset.freshness=model.freshness;
        if(timer)clearTimeout(timer);
        if(model.freshness==='CURRENT')timer=setTimeout(render,Math.max(200,(model.epoch+11-Date.now()/1000)*1000));
        put('fieldFreshness',model.freshness+' · '+(model.epoch===null?'unknown observation time':new Date(model.epoch*1000).toLocaleString()));
        put('fieldMode',model.mode); put('fieldRequested',(request && request.target) || model.target || 'None reported');
        if (request) {
            if (model.freshness==='CURRENT' && (request.phase==='accepted' || request.phase==='pending') && model.mode===request.target) request.phase='observed';
            put('fieldAction','Mode request '+request.target+': '+request.phase+' · '+(request.phase==='observed'?'current mode seen in fresh state readback':'verify current state; request status is not an execution receipt'));
        }
        put('fieldUplink',model.wifi+' · internet '+model.internet); put('fieldPortal','Captive portal: '+model.portal);
        put('fieldClient','NAT '+model.nat); put('fieldSensor',model.sensor+' · decoy '+model.decoy);
        put('fieldWarning','Display condition: '+model.warning+' (not an operating mode)');
    }
    document.getElementById('fieldToggle').addEventListener('click',function(){ root.hidden=!root.hidden;this.setAttribute('aria-pressed',String(!root.hidden)); });
    document.addEventListener('gadget:state',function(e){ latest=e.detail||{};failed=false;render(); });
    document.addEventListener('gadget:state-error',function(){failed=true;render();});
    document.addEventListener('gadget:mode-request',function(e){var value=e.detail||{}, target=safe(value.target).toUpperCase(); if(['SHIELD','PORTAL','SCAPEGOAT'].indexOf(target)<0)return; request={target:target,phase:safe(value.phase,20)}; render();});
    document.addEventListener('gadget:stream',function(e){put('fieldStream','Event stream: '+safe(e.detail));});
    document.addEventListener('gadget:event',function(e){
        var raw=e.detail||{}, row={time:safe(raw.timestamp,40),topic:safe(raw.topic,80),title:safe(raw.title,160),message:safe(raw.message,500),severity:safe(raw.severity,20)};
        events.unshift(row); events=events.slice(0,24);
        var list=document.getElementById('fieldEvents');list.textContent='';
        events.slice().sort(function(a,b){var rank={error:0,warning:1};return (rank[a.severity]===undefined?2:rank[a.severity])-(rank[b.severity]===undefined?2:rank[b.severity]);}).forEach(function(item){
            var li=document.createElement('li'), detail=document.createElement('details'), title=document.createElement('summary'), body=document.createElement('p');
            title.textContent=(item.severity||'unknown')+' · '+(item.time||'unknown time')+' · '+item.title;
            body.textContent='Topic: '+(item.topic||'unknown')+' · '+item.message;detail.appendChild(title);detail.appendChild(body);li.appendChild(detail);list.appendChild(li);
        });
    });
    render();
})();
