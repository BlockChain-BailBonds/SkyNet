/* Read-only CodeForge evidence. No tokens, privileged actions or persistence. */
const API='https://api.github.com/repos/BlockChain-BailBonds/SkyNet';
const $=s=>document.querySelector(s);
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=(value,cls)=>'<span class="tag '+cls+'">'+safe(value)+'</span>';
function githubLink(url,title){
  try{const u=new URL(String(url));if(u.protocol==='https:'&&u.hostname==='github.com')return '<a rel="noopener noreferrer" target="_blank" href="'+safe(u.href)+'">'+safe(title)+'</a>';}catch{}
  return safe(title);
}
async function get(path){
  const abort=new AbortController();const timer=setTimeout(()=>abort.abort(),10000);
  try{
    const res=await fetch(API+path,{headers:{Accept:'application/vnd.github+json'},cache:'no-store',signal:abort.signal});
    if(!res.ok)throw new Error('GitHub API HTTP '+res.status);
    return await res.json();
  }finally{clearTimeout(timer);}
}
async function reload(){
  $('#status').textContent='Fetching public GitHub evidence…';
  $('#reload').disabled=true;
  try{
    const [repo,prs,runs]=await Promise.all([get(''),get('/pulls?state=open&per_page=30'),get('/actions/runs?per_page=12')]);
    $('#repo').innerHTML=label('PUBLIC REPOSITORY','verified')+'<p>'+safe(repo.full_name)+'</p><p class="sub">This does not attest a deployed worker.</p>';
    $('#merge').innerHTML=repo.allow_auto_merge===true?label('ENABLED IN SETTINGS','unverified'):label('BLOCKED IN SETTINGS','blocked');
    $('#merge').innerHTML+='<p class="sub">Independent protected rules, exact check status and current human approval still required.</p>';
    const coding=Array.isArray(runs.workflow_runs)?runs.workflow_runs.find(x=>x.name==='SkyNet CodeForge - Isolated Self-Coding'):null;
    $('#last').innerHTML=coding?label(coding.status==='completed'?(coding.conclusion||'UNVERIFIED').toUpperCase():'IN PROGRESS',coding.conclusion==='success'?'verified':'unverified')+
      '<p>'+githubLink(coding.html_url,'Open exact workflow run')+'</p><p class="sub">'+safe(coding.created_at)+'</p>':
      label('NO VERIFIED CODING RUN','blocked');
    const selected=Array.isArray(prs)?prs.filter(x=>typeof x.head?.ref==='string'&&x.head.ref.startsWith('codeforge/')):[];
    $('#prs').innerHTML=selected.length?'<ul>'+selected.map(pr=>'<li>'+githubLink(pr.html_url,pr.title)+' · '+label('OPEN — REVIEW REQUIRED','unverified')+'<div class="sub">Branch '+safe(pr.head?.ref)+' · PR #'+safe(pr.number)+'</div></li>').join('')+'</ul>':
      '<p>No open CodeForge-generated PRs found in the first page of GitHub results.</p>';
    $('#status').textContent='GitHub public API read completed. No private gateway or live agent connection inferred.';
  }catch(e){
    $('#repo').innerHTML=label('SOURCE UNAVAILABLE','blocked');
    $('#merge').innerHTML=label('NOT VERIFIED','blocked');
    $('#last').innerHTML=label('NOT VERIFIED','blocked');
    $('#prs').textContent='Unable to verify current PR evidence.';
    $('#status').textContent='BLOCKED: '+String(e.message||'Unknown GitHub API error');
  }finally{$('#reload').disabled=false;}
}
$('#reload').addEventListener('click',reload);
reload();
