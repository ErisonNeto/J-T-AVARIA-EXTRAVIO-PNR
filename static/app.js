/* J&T Qualidade: Avaria / Extravio / PNR. Sem CDN e sem dependências externas. */
'use strict';
const $ = (id) => document.getElementById(id);
const brn = new Intl.NumberFormat('pt-BR', {maximumFractionDigits:0});
const brl = new Intl.NumberFormat('pt-BR', {style:'currency',currency:'BRL'});
const n = (x) => brn.format(Number(x)||0);
const money = (c) => brl.format((Number(c)||0)/100);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const isoBR = (s) => /^\d{4}-\d{2}-\d{2}$/.test(s||'') ? `${s.slice(8,10)}/${s.slice(5,7)}/${s.slice(0,4)}` : '—';
const short = (v, max=50) => String(v||'').length>max?String(v).slice(0,max-1)+'…':String(v||'');
const validDate = (s) => /^\d{4}-\d{2}-\d{2}$/.test(s||'');
const dateObj = (s) => new Date(s+'T12:00:00');
const localISO = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const shiftDay = (s, delta) => {const d=dateObj(s);d.setDate(d.getDate()+delta);return localISO(d)};
const monday = (s) => {const d=dateObj(s); d.setDate(d.getDate()-(d.getDay()+6)%7);return localISO(d)};
const sum = (rows) => rows.reduce((a,r)=>a+Number(r.valor_centavos||0),0);
const filterIds = ['uf','coordenador','supervisor','sc','base','secundaria','modalidade'];
let data = {meta:{datas:{}},rows:[]};
let active = 'Avaria';
let allForTab = [], filtered = [];
let page = 1;
let showAllBases=false,showAllManagers=false;
let chartMetric='count',chartPeriod='day',rankMetric='value';
let toastHandle;

function notify(message){const t=$('toast');t.textContent=message;t.classList.add('show');clearTimeout(toastHandle);toastHandle=setTimeout(()=>t.classList.remove('show'),3500)}
function unique(values){return [...new Set(values.filter(v=>v!==null&&v!==undefined&&String(v).trim()))].sort((a,b)=>String(a).localeCompare(String(b),'pt-BR'))}
function fillSelect(id, values, fallback){const el=$(id),prev=el.value;el.innerHTML='<option value="">'+esc(fallback)+'</option>'+unique(values).map(v=>`<option value="${esc(v)}">${esc(short(v,50))}</option>`).join('');if(prev&&!Array.from(el.options).some(x=>x.value===prev)){el.insertAdjacentHTML('beforeend',`<option value="${esc(prev)}">${esc(prev)} (fora da aba)</option>`)}el.value=prev;}
function managers(row){return unique([row.coordenador,row.supervisor]);}
function categoryRows(){return data.rows.filter(r=>r.tipo===active);}
function filtersWithoutDate(rows){const q=$('search').value.trim().toLowerCase();return rows.filter(r=>{
  if($('uf').value && r.uf!==$('uf').value)return false;
  if($('base').value && r.base!==$('base').value)return false;
  if($('coordenador').value && r.coordenador!==$('coordenador').value)return false;
  if($('supervisor').value && r.supervisor!==$('supervisor').value)return false;
  if($('sc').value && !managers(r).includes($('sc').value))return false;
  if($('secundaria').value && r.secundaria!==$('secundaria').value)return false;
  if(active==='Extravio' && $('modalidade').value && r.modalidade!==$('modalidade').value)return false;
  return !q || (r.remessa||'').toLowerCase().includes(q) || (r.declaracao||'').toLowerCase().includes(q);
});}
function inPeriod(rows,start,end){return rows.filter(r=>(!start||r.data>=start)&&(!end||r.data<=end));}
function refreshFilters(){
  allForTab=categoryRows();
  fillSelect('uf',allForTab.map(r=>r.uf),'Todas');
  fillSelect('base',allForTab.map(r=>r.base),'Todas');
  fillSelect('coordenador',allForTab.map(r=>r.coordenador),'Todos');
  fillSelect('supervisor',allForTab.map(r=>r.supervisor),'Todos');
  fillSelect('sc',allForTab.flatMap(managers),'Todos');
  fillSelect('secundaria',allForTab.map(r=>r.secundaria),'Todas');
  fillSelect('modalidade',allForTab.map(r=>r.modalidade),'Todas');
  $('originField').classList.toggle('hidden',active!=='Extravio');
  for(const type of ['Avaria','Extravio','PNR'])$('tab'+type).textContent=n(data.rows.filter(r=>r.tipo===type).length);
  document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('is-active',b.dataset.tab===active); b.setAttribute('aria-selected',b.dataset.tab===active?'true':'false')});
}
function setup(){
  const {min,max} = data.meta.datas || {};
  $('dateEnd').value=max||'';
  $('dateStart').value=max? (min && shiftDay(max,-6)<min?min:shiftDay(max,-6)) : '';
  $('lastDate').textContent=isoBR(max);
  $('sourceInfo').textContent='Dados da JT API • PostgreSQL';
  refreshFilters();
  for(const id of [...filterIds,'dateStart','dateEnd','search'])$(id).addEventListener(id==='search'?'input':'change',()=>{page=1; render()});
  $('resetFilters').addEventListener('click',()=>{for(const id of filterIds)$(id).value='';$('search').value='';period('7');});
  document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{if(active!==b.dataset.tab){active=b.dataset.tab;$('modalidade').value='';page=1;showAllBases=false;showAllManagers=false;refreshFilters();render()}}));
  document.querySelectorAll('[data-period]').forEach(b=>b.addEventListener('click',()=>period(b.dataset.period)));
  document.querySelectorAll('[data-chartmetric]').forEach(b=>b.addEventListener('click',()=>{chartMetric=b.dataset.chartmetric;activeButton('[data-chartmetric]',b);renderChart()}));
  document.querySelectorAll('[data-chartperiod]').forEach(b=>b.addEventListener('click',()=>{chartPeriod=b.dataset.chartperiod;activeButton('[data-chartperiod]',b);renderChart()}));
  document.querySelectorAll('[data-rankmetric]').forEach(b=>b.addEventListener('click',()=>{rankMetric=b.dataset.rankmetric;activeButton('[data-rankmetric]',b);renderRanks()}));
  $('moreBases').addEventListener('click',()=>{showAllBases=!showAllBases;renderRanks()});
  $('moreManagers').addEventListener('click',()=>{showAllManagers=!showAllManagers;renderRanks()});
  $('pagePrev').addEventListener('click',()=>{page--;renderDetails()});
  $('pageNext').addEventListener('click',()=>{page++;renderDetails()});
  $('downloadDetails').addEventListener('click',exportDetails);
  $('downloadBases').addEventListener('click',exportBases);
  $('downloadBases2').addEventListener('click',exportBases);
  $('downloadManagers').addEventListener('click',exportManagers);
  $('downloadSecondary').addEventListener('click',exportSecondary);
  document.addEventListener('click',handleActions);
  renderQuality();render();
}
function activeButton(query,button){document.querySelectorAll(query).forEach(x=>x.classList.toggle('on',x===button));}
function period(mode){const {min,max}=data.meta.datas||{};if(!max){notify('Importe um histórico para selecionar o período.');return;}
  let start=min,end=max;if(mode==='last')start=max;else if(mode==='7')start=shiftDay(max,-6);else if(mode==='month')start=max.slice(0,7)+'-01';
  if(min&&start<min)start=min;$('dateStart').value=start;$('dateEnd').value=end;page=1;render();
  document.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('active',b.dataset.period===mode));
}
function render(){
  const start=$('dateStart').value,end=$('dateEnd').value;
  if(start&&end&&start>end){notify('Data inicial posterior à data final.');filtered=[]}else filtered=inPeriod(filtersWithoutDate(allForTab),start,end);
  $('filterResult').innerHTML=`<b>${n(filtered.length)}</b> ocorrências de ${esc(active)} · <b>${money(sum(filtered))}</b>`;
  document.querySelectorAll('[data-period]').forEach(b=>b.classList.remove('active'));
  renderKpis();renderChart();renderRanks();renderSecondary();renderDetails();
}
function currentContextRows(){return filtersWithoutDate(allForTab)}
function renderKpis(){
  const amount=sum(filtered), cnt=filtered.length;
  $('kValue').textContent=money(amount);$('kCount').textContent=n(cnt);
  $('kBases').textContent=n(new Set(filtered.map(r=>r.codigo_base||r.base)).size);
  $('kManagers').textContent=n(new Set(filtered.flatMap(managers)).size);
  $('kTicket').textContent=money(cnt?Math.round(amount/cnt):0);
  const start=$('dateStart').value,end=$('dateEnd').value;
  const all=currentContextRows();
  const shifted=inPeriod(all,start?shiftDay(start,-7):'',end?shiftDay(end,-7):'');
  $('kPrevious').textContent=n(shifted.length)+' ocorr.';
  $('kPreviousHint').textContent=`${money(sum(shifted))} · ${shifted.length?deltaLabel(cnt,shifted.length):'sem base de comparação'}`;
  if(end&&validDate(end)){
    const thisWeekMonday=monday(end), lastStart=shiftDay(thisWeekMonday,-7),lastEnd=shiftDay(thisWeekMonday,-1);
    const prevWeek=inPeriod(all,lastStart,lastEnd);
    $('kLastWeek').textContent=n(prevWeek.length)+' ocorr.';
    $('kLastWeekHint').textContent=isoBR(lastStart)+' a '+isoBR(lastEnd)+' · '+money(sum(prevWeek));
    const oldDay=shiftDay(end,-7),same=inPeriod(all,oldDay,oldDay);
    $('kSameDay').textContent=n(same.length)+' ocorr.';
    $('kSameDayHint').textContent=isoBR(oldDay)+' · '+money(sum(same));
  }else{$('kLastWeek').textContent='—';$('kSameDay').textContent='—';$('kLastWeekHint').textContent='Sem período';$('kSameDayHint').textContent='Sem período'}
}
function deltaLabel(current,previous){const pct=previous?((current-previous)/previous*100):0;return (pct>0?'+':'')+pct.toLocaleString('pt-BR',{maximumFractionDigits:1})+'% no volume'}
function grouping(rows,keyfn){const map=new Map();for(const r of rows){const key=keyfn(r);if(!key)continue;const p=map.get(key)||{key,count:0,value:0,items:[]};p.count++;p.value+=Number(r.valor_centavos||0);p.items.push(r);map.set(key,p)}return [...map.values()]}
function groupChart(rows,dayOffset=0){const map=new Map();const keyfn=(r)=>{if(!validDate(r.data))return null;const d=dayOffset?shiftDay(r.data,dayOffset):r.data;return chartPeriod==='week'?monday(d):d};for(const x of grouping(rows,keyfn))map.set(x.key,x);return map}
function seriesDates(start,end){if(!validDate(start)||!validDate(end))return[];const dates=[];let cursor=chartPeriod==='week'?monday(start):start;const step=chartPeriod==='week'?7:1;while(cursor<=end&&dates.length<800){dates.push(cursor);cursor=shiftDay(cursor,step)}return dates}
function chartCoords(arr,max,w,h,left,right,top,bottom){const ww=w-left-right,hh=h-top-bottom;return arr.map((v,i)=>[left+(arr.length===1?ww/2:i/(arr.length-1)*ww),top+hh-(max?Math.max(0,v)/max*hh:0)])}
function renderChart(){
  $('chartTitle').textContent='Evolução '+(chartPeriod==='day'?'diária':'semanal')+' — '+active;
  const start=$('dateStart').value,end=$('dateEnd').value;
  const dates=seriesDates(start,end);const el=$('chart');
  if(!dates.length){el.innerHTML='<div class="empty" style="padding-top:120px!important">Selecione um período válido para visualizar a evolução.</div>';$('chartCoverage').textContent='Sem datas';return}
  const base=currentContextRows(),startPrev=shiftDay(start,-7),endPrev=shiftDay(end,-7);
  const curMap=groupChart(inPeriod(base,start,end));const prevMap=groupChart(inPeriod(base,startPrev,endPrev),7);
  const metric=(r)=>chartMetric==='count'?(r?.count||0):((r?.value||0)/100);
  const current=dates.map(k=>metric(curMap.get(k))),previous=dates.map(k=>metric(prevMap.get(k)));
  const w=1020,h=320,left=72,right=22,top=15,bottom=45,max=Math.max(1,...current,...previous);
  const yMax=Math.ceil(max/4)*4||4;const pts=chartCoords(current,yMax,w,h,left,right,top,bottom),ref=chartCoords(previous,yMax,w,h,left,right,top,bottom);
  const path=(p)=>p.map(([x,y],i)=>`${i?'L':'M'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const baseY=h-bottom;let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Evolução de ${esc(active)}"><defs><linearGradient id="fadeRed" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#d71920" stop-opacity=".18"/><stop offset="100%" stop-color="#d71920" stop-opacity="0"/></linearGradient></defs>`;
  for(let i=0;i<=4;i++){const value=yMax*i/4,y=baseY-(baseY-top)*i/4;svg+=`<line x1="${left}" y1="${y}" x2="${w-right}" y2="${y}" stroke="#e5e9ef" stroke-dasharray="3 5"/><text x="${left-12}" y="${y+4}" text-anchor="end" fill="#8792a0" font-size="12">${esc(chartMetric==='value'?'R$ '+compact(value):compact(value))}</text>`}
  svg+=`<path d="${path(pts)} L ${pts[pts.length-1][0]},${baseY} L ${pts[0][0]},${baseY} Z" fill="url(#fadeRed)"/><path d="${path(ref)}" stroke="#b4bdc9" stroke-width="2.6" stroke-dasharray="7 6" fill="none" stroke-linejoin="round"/><path d="${path(pts)}" stroke="#d71920" stroke-width="3.1" fill="none" stroke-linejoin="round"/>`;
  const maxLabels=Math.min(dates.length,8);const ticks=new Set(Array.from({length:maxLabels},(_,i)=>Math.round(i*(dates.length-1)/Math.max(1,maxLabels-1))));
  dates.forEach((k,i)=>{const [x,y]=pts[i];if(dates.length<=65)svg+=`<circle cx="${x}" cy="${y}" r="3.9" fill="#fff" stroke="#d71920" stroke-width="2"><title>${esc(chartPeriod==='week'?'Semana de '+isoBR(k):isoBR(k))}: ${esc(chartMetric==='count'?n(current[i])+' ocorrências':brl.format(current[i]))}</title></circle>`;if(ticks.has(i))svg+=`<text x="${x}" y="${h-13}" font-size="11" fill="#8d98a6" text-anchor="middle">${k.slice(8,10)}/${k.slice(5,7)}</text>`});
  svg+='</svg>';el.innerHTML=svg;
  $('chartCoverage').textContent=n(dates.length)+(chartPeriod==='week'?' semanas (seg–dom)':' dias')+' · '+isoBR(start)+' a '+isoBR(end);
}
function compact(value){if(value>=1e6)return (value/1e6).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mi';if(value>=1e3)return (value/1e3).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mil';return Number(value).toLocaleString('pt-BR',{maximumFractionDigits:1})}
function orderGroups(groups){return groups.sort((a,b)=>rankMetric==='count'?(b.count-a.count||b.value-a.value):(b.value-a.value||b.count-a.count))}
function baseGroups(){return orderGroups(grouping(filtered,r=>r.codigo_base||r.base||'Base não informada'))}
function managerGroups(){const map=new Map();for(const r of filtered){const seen=new Set();for(const [name,role] of [[r.coordenador,'Coordenador'],[r.supervisor,'Supervisor']]){if(!name)continue;const k=name+'\u001f'+role;if(seen.has(k))continue;seen.add(k);let g=map.get(k);if(!g){g={key:k,name,role,count:0,value:0,items:[]};map.set(k,g)}g.count++;g.value+=Number(r.valor_centavos||0);g.items.push(r)}}return orderGroups([...map.values()])}
function baseLabel(group){return group.items[0]?.base||'Não informado'}
function renderRanks(){const bases=baseGroups(),managersList=managerGroups();const topBase=showAllBases?bases:bases.slice(0,10),topM=showAllManagers?managersList:managersList.slice(0,10),bigBase=bases[0]?.[rankMetric]||1,bigM=managersList[0]?.[rankMetric]||1;
  $('baseLabel').textContent=n(bases.length)+' bases no recorte';
  $('baseRows').innerHTML=topBase.map(g=>{const r=g.items[0];return `<tr><td><span class="main-name">${esc(baseLabel(g))}</span><span class="minor">${esc(r.codigo_base||'Sem código')} · ${esc(r.uf||'—')}</span><div class="tiny-bar"><span style="width:${Math.min(100,g[rankMetric]/bigBase*100)}%"></span></div></td><td><span class="main-name">${esc(short(r.coordenador||'Não informado',37))}</span><span class="minor">Sup.: ${esc(short(r.supervisor||'Não informado',36))}</span></td><td class="num">${n(g.count)}</td><td class="num"><b>${money(g.value)}</b></td></tr>`}).join('')||'<tr><td colspan="4" class="empty">Nenhuma base encontrada.</td></tr>';
  $('managerRows').innerHTML=topM.map(g=>`<tr><td><span class="main-name">${esc(short(g.name,43))}</span><div class="tiny-bar"><span style="width:${Math.min(100,g[rankMetric]/bigM*100)}%"></span></div></td><td>${esc(g.role)}</td><td class="num">${n(g.count)}</td><td class="num"><b>${money(g.value)}</b></td></tr>`).join('')||'<tr><td colspan="4" class="empty">Nenhum responsável cadastrado.</td></tr>';
  $('moreBases').textContent=showAllBases?'Mostrar top 10':'Ver todas as bases ('+n(bases.length)+')';
  $('moreManagers').textContent=showAllManagers?'Mostrar top 10':'Ver todos os S/C ('+n(managersList.length)+')';
}
function secondaryGroups(){return grouping(filtered,r=>JSON.stringify([r.primaria||'',r.secundaria||''])).map(x=>({...x,primaria:x.items[0].primaria,secundaria:x.items[0].secundaria})).sort((a,b)=>b.value-a.value||b.count-a.count)}
function renderSecondary(){$('secondaryRows').innerHTML=secondaryGroups().map(g=>`<tr><td>${esc(g.primaria)}</td><td><span class="main-name">${esc(g.secundaria||'Sem detalhamento')}</span></td><td class="num">${n(g.count)}</td><td class="num"><b>${money(g.value)}</b></td><td><button class="tiny-link" data-secondary="${esc(g.secundaria)}" type="button">Filtrar</button></td></tr>`).join('')||'<tr><td colspan="5" class="empty">Nenhuma anomalia secundária no período.</td></tr>'}
function renderDetails(){const max=Math.max(1,Math.ceil(filtered.length/25));page=Math.min(Math.max(1,page),max);const list=filtered.slice((page-1)*25,page*25);
  $('detailRows').innerHTML=list.map((r,i)=>`<tr><td>${esc(isoBR(r.data))}</td><td><b>${esc(r.remessa)}</b><span class="minor">${esc(r.declaracao)}</span></td><td title="${esc(r.secundaria)}">${esc(short(r.secundaria,48))}</td><td>${esc(r.base||'—')}</td><td>${esc(short(r.coordenador||'Não informado',26))}</td><td>${esc(short(r.supervisor||'Não informado',26))}</td><td class="num"><b>${money(r.valor_centavos)}</b></td><td><button class="row-more" data-detail="${(page-1)*25+i}" type="button">Ver</button></td></tr>`).join('')||'<tr><td colspan="8" class="empty">Nenhuma remessa para os filtros aplicados.</td></tr>';
  const a=list.length?(page-1)*25+1:0,b=list.length?(page-1)*25+list.length:0;
  $('detailCount').textContent=n(filtered.length)+' responsabilizações · Cada registro mantém seu tipo primário e secundário original.';
  $('pageStatus').textContent=`${n(a)}–${n(b)} de ${n(filtered.length)} · Página ${page} de ${max}`;$('pagePrev').disabled=page<=1;$('pageNext').disabled=page>=max;
}
function handleActions(ev){const button=ev.target.closest('[data-secondary],[data-detail]');if(!button)return;
  if(button.hasAttribute('data-secondary')){$('secundaria').value=button.dataset.secondary;page=1;render();$('detalhamento').scrollIntoView({behavior:'smooth'});notify('Filtrado pela anomalia secundária.');return}
  const idx=Number(button.dataset.detail),r=filtered[idx],tr=button.closest('tr');if(!r||!tr)return;
  if(tr.nextElementSibling?.classList.contains('details-row')){tr.nextElementSibling.remove();button.textContent='Ver';return}
  document.querySelectorAll('.details-row').forEach(x=>x.remove());document.querySelectorAll('[data-detail]').forEach(x=>x.textContent='Ver');
  const child=document.createElement('tr');child.className='details-row';child.innerHTML=`<td colspan="8"><div class="detail-expanded"><div><h4>Declaração / status</h4><p>${esc(r.declaracao)}\n${esc(r.status)}</p></div><div><h4>R/M · base · código</h4><p>${esc(r.rm)}\n${esc(r.base)} · ${esc(r.codigo_base)}</p></div><div><h4>Gestão cadastrada</h4><p>Coordenador: ${esc(r.coordenador||'Não informado')}\nSupervisor: ${esc(r.supervisor||'Não informado')}</p></div><div class="wide"><h4>Classificação original (D / E)</h4><p>${esc(r.primaria)}\n${esc(r.secundaria)}</p></div><div><h4>Data da declaração</h4><p>${esc(isoBR(r.declarada_em))}</p></div><div class="wide"><h4>Descrição da anomalia (AB)</h4><p>${esc(r.descricao||'Não informada')}</p></div><div><h4>Decisão da arbitragem (AK)</h4><p>${esc(r.comentario_decisao||'Não informada')}</p></div><div><h4>Contestação (AL)</h4><p>${esc(r.comentario_contestacao||'Não informada')}</p></div></div></td>`;
  tr.after(child);button.textContent='Fechar';
}
function renderQuality(){const m=data.meta||{};const entries=[['Responsabilizações Orlean no banco',m.total_ativos],['Bases do R/M com ocorrência',m.bases_ofensoras],['Sem correspondência global na Gestão',m.sem_correspondencia_global]];
  $('qualityStats').innerHTML=entries.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${v===null||v===undefined?'Não apurado':n(v)}</dd></div>`).join('');
  $('unmatchedRows').innerHTML='<tr><td colspan="2" class="empty">Verifique as bases sem vínculo na rotina ETL da JT API. O dashboard não inventa responsáveis nem exibe outras regionais.</td></tr>';
}
function csvCell(value,asCode=false){let s=String(value??'').replace(/\r?\n/g,' ');if(asCode&&s)s='\t'+s;else if(/^[=+@\-\t\r]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"'}
function downloadCSV(file,headers,records,codeCols=[]){const lines=['sep=;',headers.map(x=>csvCell(x)).join(';'),...records.map(row=>row.map((v,i)=>csvCell(v,codeCols.includes(i))).join(';'))];const blob=new Blob(['\uFEFF',lines.join('\r\n')],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=file;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2500);notify('Exportação gerada: '+file)}
function stamp(){return ($('dateStart').value||'inicio').replace(/-/g,'')+'_'+($('dateEnd').value||'fim').replace(/-/g,'')}
function exportDetails(){const headers=['Nº declaração','Nº remessa','Data apuração','Data fechamento','Data declaração','Indicador','Origem / modalidade','Anomalia primária (D)','Anomalia secundária (E)','Base responsável original (AE)','Base vinculada Gestão','Código base','UF','R/M','Coordenador','Supervisor','Status da arbitragem','Valor a pagar R$ (AG)','Descrição (AB)','Decisão (AK)','Contestação (AL)','Coerente? (Sim/Não)','Observação do S/C'];
  const rows=filtered.map(r=>[r.declaracao,r.remessa,isoBR(r.data),isoBR(r.fechada_em),isoBR(r.declarada_em),r.tipo,r.modalidade,r.primaria,r.secundaria,r.base_responsavel,r.base,r.codigo_base,r.uf,r.rm,r.coordenador,r.supervisor,r.status,(r.valor_centavos/100).toFixed(2).replace('.',','),r.descricao,r.comentario_decisao,r.comentario_contestacao,'','']);
  downloadCSV('JT_'+active.toUpperCase()+'_remessas_'+stamp()+'.csv',headers,rows,[1,11]);}
function exportBases(){const rows=baseGroups().map(g=>{const r=g.items[0];return[r.base,r.codigo_base,r.uf,r.rm,r.coordenador,r.supervisor,g.count,(g.value/100).toFixed(2).replace('.',',')]});downloadCSV('JT_'+active.toUpperCase()+'_bases_'+stamp()+'.csv',['Base','Código','UF','R/M','Coordenador','Supervisor','Ocorrências','Valor R$'],rows,[1]);}
function exportManagers(){const rows=managerGroups().map(g=>[g.name,g.role,g.count,(g.value/100).toFixed(2).replace('.',',')]);downloadCSV('JT_'+active.toUpperCase()+'_responsaveis_'+stamp()+'.csv',['Responsável','Função','Ocorrências','Valor R$'],rows);}
function exportSecondary(){const rows=secondaryGroups().map(g=>[active,g.primaria,g.secundaria,g.count,(g.value/100).toFixed(2).replace('.',',')]);downloadCSV('JT_'+active.toUpperCase()+'_secundarias_'+stamp()+'.csv',['Indicador','Primária (D)','Secundária (E)','Ocorrências','Valor R$'],rows);}
async function load(){
  try {
    const response=await fetch('/api/dados',{cache:'no-store'});
    if(!response.ok){
      let body={};
      try{body=await response.json()}catch{}
      throw new Error(body.detail||('JT API retornou HTTP '+response.status));
    }
    data=await response.json();
    if(!Array.isArray(data.rows))throw new Error('Formato inesperado da API de dados.');
    setup();
    if(!data.rows.length)notify('Não há ocorrências no banco para o R/M Orlean. Verifique a carga na JT API.');
  }catch(error){
    console.error('JT API indisponível:',error);
    document.querySelector('.container').innerHTML=
      '<section class="panel error-banner"><h2>Dados indisponíveis na JT API</h2>'+
      '<p>'+esc(error.message)+'</p>'+
      '<p>O painel lê exclusivamente o PostgreSQL da VM pela JT API. Não existe importação de XLSX pela interface. Confirme a tabela jt_arbitragem_ocorrencias e as variáveis JT_API_URL / JT_API_KEY do serviço.</p>'+
      '<button class="btn btn-primary" type="button" onclick="location.reload()">Tentar novamente</button></section>';
  }
}
load();