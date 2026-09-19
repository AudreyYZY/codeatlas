/* Local in-memory transport for the exact same explorer UI. */
function snapshotSubgraph(graph, params, isCall) {
  let focus=params.get("focus");
  if (isCall && focus) focus="s:"+focus;
  const depth=Number(params.get("depth") || 2), direction=params.get("direction") || "both";
  let keep=new Set(graph.nodes.map(n=>n.id)); const levels={};
  if (focus) {
    keep=new Set([focus]); levels[focus]=0;
    [["downstream",1],["upstream",-1]].forEach(([walk,sign])=>{
      if(direction!=="both"&&direction!==walk)return;
      const visited=new Set([focus]);let frontier=[focus];
      for(let i=0;i<depth;i++) {
        const next=new Set();
        graph.edges.forEach(e=>{
          const from=walk==="downstream"?e.source:e.target,to=walk==="downstream"?e.target:e.source;
          if(frontier.includes(from)&&!visited.has(to))next.add(to);
        });
        next.forEach(n=>{visited.add(n);keep.add(n);if(!(n in levels))levels[n]=sign*(i+1);});
        frontier=[...next];
      }
    });
  }
  const selected=graph.nodes.filter(n=>keep.has(n.id)&&(!isCall||params.get("include_unresolved")!=="false"||!n.unresolved));
  selected.sort((a,b)=>(a.id!==focus)-(b.id!==focus)||Math.abs(levels[a.id]||0)-Math.abs(levels[b.id]||0)||a.id.localeCompare(b.id));
  const limit=Number(params.get("limit")||400),total=selected.length;
  const nodes=selected.slice(0,limit).map(n=>({...n,depth:Math.abs(levels[n.id]||0),layer:levels[n.id]||0,is_focus:n.id===focus}));
  keep=new Set(nodes.map(n=>n.id));
  return {...graph,nodes,edges:graph.edges.filter(e=>keep.has(e.source)&&keep.has(e.target)),
    total_nodes:total,shown_nodes:nodes.length,truncated:total>nodes.length};
}
function snapshotApi(path, opts) {
  if(opts && opts.method && opts.method!=="GET")throw new Error("Read-only snapshot. Run CodeAtlas locally to edit indexes.");
  const d=window.CODEATLAS_SNAPSHOT;
  const url=new URL(path,"http://snapshot.local");
  if(url.pathname==="/api/projects")return {projects:[{name:d.name,...d.report.stats}]};
  const action=url.pathname.split("/").pop(),params=url.searchParams;
  if(action==="report")return d.report;
  if(action==="files")return {files:d.files};
  if(action==="structure")return d.structure;
  if(action==="relationships") {
    const graph=snapshotRelationships(d.relationships,params);
    const focus=params.get("focus");if(focus&&!graph.nodes.some(n=>n.id===focus))throw new Error("Unknown or excluded file");
    return snapshotSubgraph(graph,params,false);
  }
  if(action==="architecture")return snapshotArchitecture(d.relationships,params);
  if(action==="graph")return snapshotSubgraph(d.graph,params,false);
  if(action==="callgraph")return snapshotSubgraph(d.calls,params,true);
  if(action==="cycles")return {cycles:d.report.cycles};
  if(action==="file")return d.details[params.get("path")];
  if(action==="search") {
    const q=params.get("q").toLowerCase();
    return {symbols:d.structure.symbols.filter(s=>s.name.toLowerCase().includes(q)).slice(0,40),
      files:d.files.filter(f=>f.rel_path.toLowerCase().includes(q)).slice(0,40)};
  }
  if(action==="symbol") {
    const matches=d.structure.symbols.filter(s=>s.name===params.get("name"));
    if(!matches.length)throw new Error("Symbol not found");
    const primary=params.has("symbol_id")?matches.find(s=>s.id===Number(params.get("symbol_id"))):matches[0];
    if(!primary)throw new Error("Declaration not found");
    const id="s:"+primary.id;
    return {matches,primary,callers:d.calls.edges.filter(e=>e.target===id).map(e=>{
      const n=d.calls.nodes.find(n=>n.id===e.source);return {caller_name:n.label,rel_path:n.path,line:e.sites[0]};}),
      callees:d.calls.edges.filter(e=>e.source===id).map(e=>({callee_name:d.calls.nodes.find(n=>n.id===e.target).label})),
      chain:[],mermaid:"",note:d.calls.note};
  }
  if(action==="mermaid") {
    const graph=snapshotSubgraph(d.graph,params,false);
    const ids=Object.fromEntries(graph.nodes.map((n,i)=>[n.id,"n"+i]));
    const label=s=>s.replaceAll('"',"'").replaceAll("\\","/").replaceAll("[","(").replaceAll("]",")");
    return "graph TD\n"+graph.edges.map(e=>`  ${ids[e.source]}["${label(e.source)}"] --> ${ids[e.target]}["${label(e.target)}"]`).join("\n");
  }
  throw new Error("Unavailable in offline snapshot");
}

function snapshotRelationships(graph,params) {
  const nodes=graph.nodes.filter(n=>params.get("include_tests")==="true"||!n.is_test),keep=new Set(nodes.map(n=>n.id));
  const kind=params.get("kind")||"all";
  const edges=graph.edges.filter(e=>keep.has(e.source)&&keep.has(e.target)&&(kind==="all"||(kind==="data"?["argument","return","handoff"].includes(e.kind):e.kind===kind)));
  return {...graph,nodes,edges,total_nodes:nodes.length,shown_nodes:nodes.length,truncated:false};
}
function snapshotArchitecture(graph,params) {
  const scope=new URLSearchParams(params);scope.set("kind","all");
  graph=snapshotRelationships(graph,scope);
  const level=Number(params.get("level")||2),modules=new Map(),membership=new Map(),links=new Map();
  graph.nodes.forEach(n=>{
    const id=n.path.split("/").slice(0,-1).slice(0,level).join("/")||"(root)";
    membership.set(n.id,id);
    if(!modules.has(id))modules.set(id,{id,label:id,files:[],lines:0,role:null});
    modules.get(id).files.push(n.path);modules.get(id).lines+=n.lines;
  });
  graph.edges.forEach(e=>{
    const source=membership.get(e.source),target=membership.get(e.target);if(source===target)return;
    const key=JSON.stringify([source,target,e.kind]);
    if(!links.has(key))links.set(key,{source,target,kind:e.kind,count:0,evidence:[]});
    const edge=links.get(key);edge.count+=e.count;
    edge.evidence.push(...e.evidence.slice(0,10).map(item=>({...item,source_file:e.source,target_file:e.target})));
  });
  const degree=new Map([...modules.keys()].map(id=>[id,0]));
  links.forEach(e=>{degree.set(e.source,degree.get(e.source)+e.count);degree.set(e.target,degree.get(e.target)+e.count);});
  const all=[...modules.values()].sort((a,b)=>degree.get(b.id)-degree.get(a.id)||a.id.localeCompare(b.id));
  const nodes=all.slice(0,Number(params.get("limit")||80)),keep=new Set(nodes.map(n=>n.id));
  return {...graph,nodes,edges:[...links.values()].filter(e=>keep.has(e.source)&&keep.has(e.target)).map(e=>({...e,evidence:e.evidence.slice(0,100)})),
    total_nodes:all.length,shown_nodes:nodes.length,truncated:all.length>nodes.length,
    note:"Modules are grouped by source directory; arrows retain indexed source evidence. "+graph.note};
}
