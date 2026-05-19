(function(){
  const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://localhost:8000'
    : (localStorage.getItem('API_BASE') || 'http://localhost:8000');
  document.getElementById('apiUrl').textContent = API_BASE;

  const textInput = document.getElementById('textInput');
  const submitBtn = document.getElementById('submitBtn');
  const submitStatus = document.getElementById('submitStatus');
  const jobListEl = document.getElementById('jobList');
  const refreshJobs = document.getElementById('refreshJobs');
  const resultSection = document.getElementById('result');
  const resultContent = document.getElementById('resultContent');
  const closeResult = document.getElementById('closeResult');

  function saveJobId(id){
    const arr = JSON.parse(localStorage.getItem('plagio_jobs')||'[]');
    if(!arr.includes(id)) arr.unshift(id);
    localStorage.setItem('plagio_jobs', JSON.stringify(arr.slice(0,50)));
  }
  function loadJobIds(){
    return JSON.parse(localStorage.getItem('plagio_jobs')||'[]');
  }

  async function submitText(){
    const text = textInput.value.trim();
    if(!text) return;
    submitBtn.disabled = true;
    submitStatus.textContent = 'Submitting...';
    try{
      const res = await fetch(API_BASE + '/submit', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({content: text})
      });
      if(!res.ok) throw new Error('Submit failed: '+res.status);
      const data = await res.json();
      saveJobId(data.job_id || data.jobId || data.id);
      submitStatus.textContent = 'Submitted — job id saved.';
      textInput.value = '';
      renderJobs();
    }catch(err){
      submitStatus.textContent = 'Error: '+err.message;
    }finally{ submitBtn.disabled = false; setTimeout(()=>submitStatus.textContent='','3000'); }
  }

  async function fetchStatus(jobId){
    try{
      const res = await fetch(API_BASE + '/status/' + jobId);
      if(!res.ok) throw new Error('Status fetch failed');
      return await res.json();
    }catch(e){ return {error: e.message}; }
  }
  async function fetchResult(jobId){
    try{
      const res = await fetch(API_BASE + '/result/' + jobId);
      if(!res.ok) throw new Error('Result fetch failed');
      return await res.json();
    }catch(e){ return {error: e.message}; }
  }

  function makeJobItem(jobId, meta){
    const li = document.createElement('li');
    const left = document.createElement('div');
    const title = document.createElement('div'); title.textContent = jobId;
    const metaEl = document.createElement('div'); metaEl.className='job-meta'; metaEl.textContent = meta || '';
    left.appendChild(title); left.appendChild(metaEl);
    const actions = document.createElement('div');
    const viewBtn = document.createElement('button'); viewBtn.textContent='View';
    viewBtn.onclick = async ()=>{
      viewBtn.disabled = true;
      const result = await fetchResult(jobId);
      if(result.error) resultContent.textContent = 'Error: '+result.error;
      else resultContent.textContent = JSON.stringify(result, null, 2);
      resultSection.classList.remove('hidden');
      viewBtn.disabled = false;
    };
    const pollBtn = document.createElement('button'); pollBtn.textContent='Poll';
    pollBtn.style.marginLeft='8px';
    pollBtn.onclick = async ()=>{
      pollBtn.disabled = true; const st = await fetchStatus(jobId); alert(JSON.stringify(st)); pollBtn.disabled=false;
    };
    actions.appendChild(viewBtn); actions.appendChild(pollBtn);
    li.appendChild(left); li.appendChild(actions);
    return li;
  }

  async function renderJobs(){
    jobListEl.innerHTML='';
    const ids = loadJobIds();
    for(const id of ids){
      const status = await fetchStatus(id);
      const meta = status.error ? 'error' : (status.status || status.state || 'unknown');
      jobListEl.appendChild(makeJobItem(id, meta));
    }
  }

  submitBtn.addEventListener('click', submitText);
  refreshJobs.addEventListener('click', renderJobs);
  closeResult.addEventListener('click', ()=>resultSection.classList.add('hidden'));

  // initial render
  renderJobs();

  // periodic background poll to update statuses every 30s
  setInterval(renderJobs, 30000);
})();