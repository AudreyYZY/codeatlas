/* Evidence-backed architecture and implementation reader. No remote assets. */
"use strict";
const reader = {architecture:null,flow:null,guide:null,guideSource:null,requests:{},views:{},guideLine:null};
const relationColors = {import:'#8a8d91',call:'#2f8068',argument:'#3d79bb',return:'#8564b2',handoff:'#c58228'};
const relationNames = {import:'import dependency',call:'function call',argument:'argument input',return:'returned result',handoff:'producer → consumer'};
function readerDownload(text, name, type='text/plain') {
  const url=URL.createObjectURL(new Blob([text],{type}));
  const link=el('a',{href:url,download:name});link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function readerFiles() {
  ['#flowFocus','#guideFile'].forEach(id=>{
    const selector=$(id), previous=selector.value;
    selector.replaceChildren();
    if(id==='#flowFocus')selector.append(el('option',{value:'',text:'Whole project'}));
    state.files.forEach(f=>selector.append(el('option',{value:f.rel_path,text:f.rel_path})));
    if([...selector.options].some(o=>o.value===previous))selector.value=previous;
  });
}
async function loadArchitecture() {
  if(!state.project)return;
  const project=state.project, request=Symbol();reader.requests.architecture=request;
  const params=new URLSearchParams({level:$('#archLevel').value,include_tests:$('#archTests').checked,limit:80});
  const graph=await api(`/api/projects/${encodeURIComponent(project)}/architecture?${params}`);
  if(state.project!==project||reader.requests.architecture!==request)return;
  reader.architecture=graph;renderReaderGraph('arch',graph,$('#archKind').value,true);
}
async function loadRelationships() {
  if(!state.project)return;
  readerFiles();
  const project=state.project, request=Symbol();reader.requests.flow=request;
  const params=new URLSearchParams({kind:$('#flowKind').value,depth:$('#flowDepth').value,include_tests:$('#flowTests').checked,limit:100});
  if($('#flowFocus').value)params.set('focus',$('#flowFocus').value);
  const graph=await api(`/api/projects/${encodeURIComponent(project)}/relationships?${params}`);
  if(state.project!==project||reader.requests.flow!==request)return;
  reader.flow=graph;renderReaderGraph('flow',graph,'all',false);
}
/* Collapse cycles before assigning dependency columns. Cycles occupy one column,
   so no recursive depth heuristic can loop forever. */
function readerLayout(nodes, edges) {
  const adjacency=new Map(nodes.map(n=>[n.id,new Set()]));
  edges.forEach(e=>adjacency.get(e.source)?.add(e.target));
  const indices=new Map(),low=new Map(),stack=[],active=new Set(),components=[];let index=0;
  function visit(id) {
    indices.set(id,index);low.set(id,index++);stack.push(id);active.add(id);
    for(const next of adjacency.get(id)) {
      if(!indices.has(next)){visit(next);low.set(id,Math.min(low.get(id),low.get(next)));}
      else if(active.has(next))low.set(id,Math.min(low.get(id),indices.get(next)));
    }
    if(low.get(id)===indices.get(id)) {
      const group=[];let next;
      do{next=stack.pop();active.delete(next);group.push(next);}while(next!==id);
      components.push(group.sort());
    }
  }
  nodes.forEach(n=>{if(!indices.has(n.id))visit(n.id);});
  const owner=new Map();components.forEach((group,i)=>group.forEach(id=>owner.set(id,i)));
  const outgoing=components.map(()=>new Set()),indegree=components.map(()=>0),layers=components.map(()=>0);
  edges.forEach(e=>{const a=owner.get(e.source),b=owner.get(e.target);if(a!==b&&!outgoing[a].has(b)){outgoing[a].add(b);indegree[b]++;}});
  const queue=indegree.map((n,i)=>n===0?i:null).filter(i=>i!==null);
  for(let i=0;i<queue.length;i++){const a=queue[i];outgoing[a].forEach(b=>{layers[b]=Math.max(layers[b],layers[a]+1);if(--indegree[b]===0)queue.push(b);});}
  const columns=new Map();nodes.forEach(n=>{const level=layers[owner.get(n.id)];if(!columns.has(level))columns.set(level,[]);columns.get(level).push(n);});
  const positions=new Map();let height=220,width=340;
  columns.forEach((group,column)=>{
    group.sort((a,b)=>a.id.localeCompare(b.id));
    group.forEach((n,row)=>positions.set(n.id,{x:28+column*340,y:36+row*115}));
    width=Math.max(width,340*(column+1));height=Math.max(height,group.length*115+64);
  });
  return {positions,width,height};
}
function renderReaderGraph(prefix,graph,kind,isModule) {
  const svg=$(`#${prefix}Canvas`),ns='http://www.w3.org/2000/svg';svg.replaceChildren();
  const edges=graph.edges.filter(e=>kind==='all'||e.kind===kind);
  let visibleNodes=graph.nodes;
  if(prefix==='flow'&&!$('#flowIsolated').checked){const connected=new Set(edges.flatMap(e=>[e.source,e.target]));visibleNodes=graph.nodes.filter(n=>n.is_focus||connected.has(n.id));}
  reader.views[prefix]={...graph,nodes:visibleNodes,edges};
  // Returns point backwards relative to execution. Prefer argument/handoff
  // direction for layout; the displayed arrows retain their real directions.
  let layoutEdges=edges.filter(e=>e.kind!=='return');if(!layoutEdges.length)layoutEdges=edges;
  const {positions,width,height}=readerLayout(visibleNodes,layoutEdges);
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.dataset.width=width;svg.dataset.height=height;
  function shape(tag,attrs,parent=svg){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));parent.append(n);return n;}
  const defs=shape('defs',{});
  Object.entries(relationColors).forEach(([type,color])=>{
    const marker=shape('marker',{id:`${prefix}-${type}`,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'},defs);
    shape('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:color},marker);
  });
  edges.forEach((edge,i)=>{
    const a=positions.get(edge.source),b=positions.get(edge.target);if(!a||!b)return;
    const forward=b.x>a.x;let x1=a.x+(forward?278:0),x2=b.x+(forward?0:278),y1=a.y+40,y2=b.y+40;
    if(a.x===b.x){x1=a.x+278;x2=b.x+278;}
    const shift=(i%5-2)*6,bend=a.x===b.x?x1+40+Math.abs(y2-y1)*0.1:(x1+x2)/2;
    const d=`M ${x1} ${y1+shift} C ${bend} ${y1+shift}, ${bend} ${y2+shift}, ${x2} ${y2+shift}`;
    const path=shape('path',{d,fill:'none',stroke:relationColors[edge.kind], 'stroke-width':Math.min(4,1.5+Math.log2(edge.count+1)*0.3),opacity:.7,'marker-end':`url(#${prefix}-${edge.kind})`});
    shape('title',{},path).textContent=`${edge.source} → ${edge.target}\n${relationNames[edge.kind]} · ${edge.count} evidence sites`;
    const hit=shape('path',{d,fill:'none',stroke:'transparent','stroke-width':14,tabindex:0,role:'button','aria-label':`${edge.source} to ${edge.target}: ${relationNames[edge.kind]}`});
    hit.style.cursor='pointer';hit.addEventListener('click',()=>readerEvidence(prefix,edge));
    hit.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();readerEvidence(prefix,edge);}});
  });
  visibleNodes.forEach(node=>{
    const {x,y}=positions.get(node.id),group=shape('g',{class:'reader-node',tabindex:0,role:'button','aria-label':node.id});
    shape('rect',{x,y,width:278,height:82,rx:10,fill:'var(--panel)',stroke:node.is_focus?'var(--accent)':'var(--line)','stroke-width':node.is_focus?2.5:1.5},group);
    const title=shape('text',{x:x+13,y:y+24,fill:'var(--ink)','font-family':'ui-monospace,monospace','font-size':12},group);
    title.textContent=node.label.length>34?node.label.slice(0,31)+'…':node.label;
    const detail=shape('text',{x:x+13,y:y+47,fill:'var(--muted)','font-size':11},group);
    detail.textContent=isModule?`${node.files.length} files · ${num(node.lines)} lines`:(node.path.length>38?'…'+node.path.slice(-36):node.path);
    const role=shape('text',{x:x+13,y:y+67,fill:'var(--muted)','font-size':10},group);
    role.textContent=isModule?(node.role||'Source module · inspect files'):`${node.language} · ${num(node.lines)} lines`;
    shape('title',{},group).textContent=node.id;
    const select=()=>isModule?readerModule(node):openFileGuide(node.path);
    group.addEventListener('click',select);group.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});
  });
  if(!visibleNodes.length)shape('text',{x:28,y:55,fill:'var(--muted)'}).textContent='No resolved relationships in this view.';
  $(`#${prefix}Note`).textContent=`${visibleNodes.length} displayed / ${graph.total_nodes} ${isModule?'modules':'files'} · ${edges.length} relationships${graph.truncated?' · limited view: focus a file to reduce scope':''}. ${graph.analysis_files} / ${graph.indexed_files} files have implementation facts. ${graph.note}`;
  $(`#${prefix}Detail`).replaceChildren(el('p',{class:'muted',text:edges.length?'Click a node or arrow for source evidence.':'No resolved relationships of this kind. Other relationship views may contain more evidence.'}));
  readerFit(prefix);
}
function readerFit(prefix) {
  const svg=$(`#${prefix}Canvas`),width=Number(svg.dataset.width||340),height=Number(svg.dataset.height||220);
  // Keep labels readable: fit smaller graphs, allow scroll for large ones.
  const scale=Math.max(.7,Math.min(1,svg.parentElement.clientWidth/width));
  svg.style.width=`${width*scale}px`;svg.style.height=`${height*scale}px`;
}
function readerModule(node) {
  const box=$('#archDetail');box.replaceChildren(el('h3',{text:node.id}),el('p',{class:'muted',text:node.role?`Directory role hint: ${node.role}. Confirm responsibility in the file implementations.`:'Read the implementation guides to establish this module’s responsibility.'}));
  node.files.forEach(path=>box.append(el('button',{class:'reader-file-button',text:path,onclick:()=>openFileGuide(path)})));
}
function readerEvidence(prefix,edge) {
  const box=$(`#${prefix}Detail`);box.replaceChildren(el('h3',{text:`${edge.source} → ${edge.target}`}),el('p',{text:`${relationNames[edge.kind]} · ${edge.count} evidence sites`}));
  edge.evidence.forEach(e=>{
    const item=el('div',{class:'reader-evidence'});
    let description;
    if(edge.kind==='import')description=`${e.via}:${e.line} imports ${e.symbol||'(module)'}${e.type_only?' (type-only)':''}`;
    else if(edge.kind==='handoff')description=`${e.producer}() → ${e.variable||'(nested return expression)'} → ${e.callee}(), argument ${e.argument_index+1}; coordinated by ${e.caller}() in ${e.via}:${e.line}`;
    else if(edge.kind==='return')description=`${e.callee}() returns a value used by ${e.caller}()${e.result?' as '+e.result:''} at ${e.via}:${e.line}`;
    else description=`${e.caller}() → ${e.callee}(${(e.arguments||[]).join(', ')}) at ${e.via}:${e.line}`;
    item.append(el('div',{class:'mono',text:description}),el('button',{text:`Read ${e.via}:${e.line}`,onclick:()=>openFileGuide(e.via,e.line)}));
    const consumer=(edge.kind==='return'?e.source_file||edge.source:e.target_file||edge.target);
    if(e.callee_line)item.append(el('button',{text:`Read ${e.callee}()`,onclick:()=>openFileGuide(consumer,e.callee_line)}));
    if(e.producer_line)item.append(el('button',{text:`Read ${e.producer}()`,onclick:()=>openFileGuide(e.source_file||edge.source,e.producer_line)}));
    box.append(item);
  });
  if(edge.evidence_truncated||edge.count>edge.evidence.length)box.append(el('p',{class:'muted',text:`Showing ${edge.evidence.length} of ${edge.count} evidence sites.`}));
}
function openFileGuide(path,line=null) {
  readerFiles();$('#guideFile').value=path;reader.guideLine=line;$('#guideFilter').value='';showTab('guide');
}
async function loadFileGuide() {
  if(!state.project)return;
  readerFiles();const path=$('#guideFile').value;if(!path)return;
  const project=state.project,request=Symbol();reader.requests.guide=request;
  $('#guideBody').replaceChildren(el('p',{class:'muted',text:'Loading indexed implementation facts…'}));
  const data=await api(`/api/projects/${encodeURIComponent(project)}/file?path=${encodeURIComponent(path)}`);
  if(project!==state.project||reader.requests.guide!==request)return;
  reader.guide=data.explanation;reader.guideSource=data.source;reader.guideStatus=data.source_status;renderFileGuide();
}
const stepNames={branch:'条件分支',loop:'循环', 'error handling':'异常处理',raises:'抛出异常',throws:'抛出异常',await:'等待异步结果',return:'返回',yield:'生成结果','resource scope':'资源管理'};
function renderFileGuide() {
  const d=reader.guide,box=$('#guideBody');if(!d)return;box.replaceChildren();
  box.append(el('h3',{class:'mono',text:d.path}),el('p',{text:d.summary}));
  if(reader.guideStatus==='changed')box.append(el('div',{class:'notice',text:'文件已在索引后修改。下方分析对应旧索引，当前源码可能不同；请重新索引。'}));
  if(!d.analysis_available)box.append(el('p',{class:'notice',text:d.note}));
  if(d.parse_has_errors)box.append(el('p',{class:'notice',text:'AST 中存在语法错误。文件事实可能不完整，因此不生成该文件的数据传递关系。'}));
  if(d.role_hint)box.append(el('p',{class:'muted',text:`目录角色提示：${d.role_hint}。${d.role_basis}`}));
  if(d.documentation)box.append(el('div',{class:'guide-context'},[el('h4',{text:'文件作用：作者的文档说明'}),el('pre',{text:d.documentation})]));
  const publicNames=d.declarations.filter(s=>s.is_export&&!s.parent_symbol).map(s=>s.parent_symbol?`${s.parent_symbol}.${s.name}`:s.name);
  box.append(el('p',{text:`公开声明（语言约定 / export）：${publicNames.slice(0,30).join(', ')||'未记录'}${publicNames.length>30?'…':''}`}));
  if(d.collaborators?.length){
    const cooperation=el('div',{class:'guide-context'},[el('h4',{text:'文件协作：可确认的内部调用'})]);
    d.collaborators.forEach(c=>cooperation.append(el('button',{class:'reader-file-button',text:`${c.name}() · ${c.path}:${c.line}`,onclick:()=>openFileGuide(c.path,c.line)})));
    box.append(cooperation);
  }
  const actions=el('div',{class:'row reader-controls'},[
    el('button',{text:'View data relationships',onclick:()=>{$('#flowFocus').value=d.path;if(d.path.split('/').some(p=>['tests','test','__tests__','fixtures'].includes(p)||/^(test_)|\.(test|spec)\./.test(p)))$('#flowTests').checked=true;showTab('flow');}}),
    el('button',{text:'View source & imports',onclick:()=>{showTab('files');loadFileDetail(d.path);}})]);box.append(actions);
  box.append(el('p',{class:'muted',text:d.note}));
  const filter=$('#guideFilter').value.toLowerCase();
  const functions=d.functions.filter(f=>`${f.parent||''}.${f.name}`.toLowerCase().includes(filter));
  if(!functions.length)box.append(el('p',{class:'muted',text:d.functions.length?'No functions match this filter.':'此文件没有已提取的函数体；查看声明、导入或源码了解类型、配置与模块初始化。'}));
  functions.forEach((f,i)=>{
    const detail=el('details',{class:'guide-function'});detail.open=i<2||(reader.guideLine&&f.line<=reader.guideLine&&reader.guideLine<=f.end_line);
    detail.append(el('summary',{text:`${f.parent?f.parent+'.':''}${f.name} · L${f.line}–${f.end_line}`}));
    detail.append(el('pre',{class:'src',text:f.signature||f.name}),el('p',{text:`输入参数：${f.parameters||'无参数列表'}。`}));
    if(f.documentation)detail.append(el('div',{class:'guide-context'},[el('b',{text:'作者说明'}),el('pre',{text:f.documentation})]));
    const returns=f.steps.filter(s=>s.kind==='return');
    detail.append(el('p',{text:returns.length?`返回表达式：${returns.map(s=>`${s.detail||'(无值)'} [L${s.line}]`).join('；')}`:'未记录显式 return；异步、生成器或表达式函数需要结合源码阅读。'}));
    const events=[...f.steps.map(s=>({...s,label:`${stepNames[s.kind]||s.kind}${s.detail?' · '+s.detail:''}`})),...f.calls.map(c=>({...c,label:`调用 ${c.ref}(${c.arguments.join(', ')})${c.result_name?' → '+c.result_name:''}${c.target?' · '+c.target.path+':'+c.target.line:' · 目标未确定'}`}))].sort((a,b)=>a.line-b.line);
    detail.append(el('h4',{text:'实现步骤（按源代码顺序；分支不保证执行）'}));
    const list=el('ol');events.forEach(event=>list.append(el('li',{class:'mono',text:`L${event.line}: ${event.label}`})));detail.append(list);
    if(!events.length)detail.append(el('p',{class:'muted',text:'没有记录调用或控制结构；可能只声明数据或执行简单表达式。'}));
    detail.append(el('button',{text:`Read source at L${f.line}`,onclick:()=>readerSource(f.line)}));box.append(detail);
  });
  if(reader.guideLine)readerSource(reader.guideLine);
}
function readerSource(line) {
  let box=$('#guideSource');if(box)box.remove();box=el('div',{class:'card',id:'guideSource'});
  box.append(el('h4',{text:`Source evidence · ${reader.guide.path}:${line}`}));
  if(!reader.guideSource){box.append(el('p',{class:'muted',text:'源码正文未包含在离线快照中或当前不可读取。上述实现事实来自索引时的 AST。'}));}
  else {
    const lines=reader.guideSource.split('\n'),start=Math.max(0,line-5),end=Math.min(lines.length,line+25),pre=el('pre',{class:'src'});
    lines.slice(start,end).forEach((text,i)=>pre.append(el('span',{class:'reader-source-line'+(start+i+1===line?' highlight':''),text:`${start+i+1}  ${text}`})));box.append(pre);
  }
  $('#guideBody').append(box);box.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function readerMermaid(graph,kind) {
  const ids=new Map(graph.nodes.map((n,i)=>[n.id,'n'+i])),label=s=>String(s).replace(/["<>\[\]{}|`\\\r\n]/g,' ').replace(/&/g,'and');
  return 'flowchart LR\n'+graph.nodes.map(n=>`  ${ids.get(n.id)}["${label(n.id)}"]`).join('\n')+'\n'+graph.edges.filter(e=>kind==='all'||e.kind===kind).map(e=>`  ${ids.get(e.source)} -->|"${e.kind}: ${e.count}"| ${ids.get(e.target)}`).join('\n')+'\n';
}
function guideMarkdown(d) {
  let text=`# ${d.path}\n\n${d.summary}\n\n${d.note}\n\n`;
  if(d.documentation)text+=`## File documentation\n\n${d.documentation}\n\n`;
  d.functions.forEach(f=>{text+=`## ${f.parent?f.parent+'.':''}${f.name} (L${f.line}–${f.end_line})\n\n${f.signature||f.name}\n\n${f.documentation||''}\n\nParameters: ${f.parameters}\n\n`;f.steps.forEach(s=>{text+=`- L${s.line}: ${s.kind} ${s.detail}\n`;});f.calls.forEach(c=>{text+=`- L${c.line}: ${c.ref}(${c.arguments.join(', ')})${c.result_name?' → '+c.result_name:''}\n`;});text+='\n';});return text;
}
['#archLevel','#archTests'].forEach(id=>$(id).addEventListener('change',()=>loadArchitecture().catch(showError)));
$('#archKind').addEventListener('change',()=>{if(reader.architecture)renderReaderGraph('arch',reader.architecture,$('#archKind').value,true);});
['#flowFocus','#flowKind','#flowDepth','#flowTests'].forEach(id=>$(id).addEventListener('change',()=>loadRelationships().catch(showError)));
$('#guideFile').addEventListener('change',()=>{reader.guideLine=null;$('#guideFilter').value='';loadFileGuide().catch(showError);});
$('#guideFilter').addEventListener('input',renderFileGuide);
$('#guideMarkdown').addEventListener('click',()=>{if(reader.guide)readerDownload(guideMarkdown(reader.guide),`${state.project}-${reader.guide.path.replaceAll('/','-')}.md`);});
['arch','flow'].forEach(prefix=>{
  $(`#${prefix}Fit`).addEventListener('click',()=>readerFit(prefix));
  $(`#${prefix}Svg`).addEventListener('click',()=>{const svg=$(`#${prefix}Canvas`).cloneNode(true),style=getComputedStyle(document.documentElement);['--panel','--ink','--muted','--accent','--line'].forEach(name=>svg.style.setProperty(name,style.getPropertyValue(name)));readerDownload(new XMLSerializer().serializeToString(svg),`${state.project}-${prefix}.svg`,'image/svg+xml');});
  $(`#${prefix}Mermaid`).addEventListener('click',()=>{const graph=reader.views[prefix];if(graph)readerDownload(readerMermaid(graph,'all'),`${state.project}-${prefix}.mmd`);});
});

$('#flowIsolated').addEventListener('change',()=>{if(reader.flow)renderReaderGraph('flow',reader.flow,'all',false);});
