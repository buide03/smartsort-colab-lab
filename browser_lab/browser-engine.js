/* SmartSort browser backend: IndexedDB, train-only ZIP, ONNX/WASM validation/test. */
'use strict';
const BrowserLab = (() => {
  const classes=['metal','paper','plastic'],names={metal:'Kim loại',paper:'Giấy',plastic:'Nhựa'};
  const text=new TextEncoder(),decoder=new TextDecoder(),urls=new Map(),states=new Map();
  let db,busy=false,runtime=null,runtimeKey=null;
  const uid=()=>crypto.randomUUID().replaceAll('-',''),now=()=>new Date().toISOString();
  const clone=x=>JSON.parse(JSON.stringify(x));
  const require=(condition,message)=>{if(!condition)throw new Error(message);};
  const sha=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
  const ready=(async()=>{
    require(window.isSecureContext,'Mở bằng HTTPS hoặc localhost để dùng bộ nhớ và mô hình trình duyệt.');
    require(navigator.locks,'Dùng Chrome/Edge/Firefox mới có hỗ trợ Web Locks.');
    await new Promise((resolve,reject)=>navigator.locks.request('smartsort-browser-tab',{ifAvailable:true},async lock=>{
      if(!lock){reject(new Error('Lab đã mở trong tab khác. Đóng tab đó rồi tải lại trang này.'));return;}
      resolve();await new Promise(()=>{});
    }));
    db=await new Promise((resolve,reject)=>{const request=indexedDB.open('smartsort-browser-v1',1);
      request.onupgradeneeded=()=>{for(const name of ['sessions','images','models'])request.result.createObjectStore(name);};
      request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
    for(const s of await all('sessions'))if(s.job?.status==='running'){
      s.job={...s.job,status:'failed',message:'Trang bị đóng/ngắt. Chạy lại cùng tác vụ; test bị ngắt chỉ được thử lại model đã chốt.'};
      if(s.job.kind==='test')s.phase='test_failed';await save(s);
    }
    await navigator.storage?.persist?.().catch(()=>false);
  })();
  function transaction(store,mode,operation){return new Promise((resolve,reject)=>{
    const tx=db.transaction(store,mode),request=operation(tx.objectStore(store));let value;
    request.onsuccess=()=>{value=request.result;};request.onerror=()=>reject(request.error);
    tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('Không lưu được dữ liệu.'));
  });}
  const get=(store,key)=>transaction(store,'readonly',s=>s.get(key));
  const put=(store,key,value)=>transaction(store,'readwrite',s=>s.put(value,key));
  const all=store=>transaction(store,'readonly',s=>s.getAll());
  const save=async s=>{await put('sessions',s.id,s);states.set(s.id,s);};
  async function load(id){const s=await get('sessions',id);require(s,'Không tìm thấy phiên trên trình duyệt này.');states.set(id,s);return s;}
  const idle=s=>require(!busy&&s.job?.status!=='running','Đang có tác vụ. Chờ hoàn tất trước khi thay đổi phiên.');
  const phase=(s,allowed)=>require(allowed.includes(s.phase),'Thao tác không hợp lệ ở giai đoạn hiện tại.');
  async function publicState(s){
    const result=clone(s);delete result._heads;
    result.counts=Object.fromEntries(classes.map(c=>[c,s.images.filter(r=>r.label===c).length]));
    result.unlabeled=s.images.filter(r=>r.label===null).length;result.excluded=s.images.filter(r=>r.label==='exclude').length;
    if(s.splits){const rows=new Map(s.images.map(r=>[r.id,r]));result.split_counts=Object.fromEntries(Object.entries(s.splits.ids).map(([part,ids])=>[part,Object.fromEntries(classes.map(c=>[c,ids.filter(i=>rows.get(i).label===c).length]))]));}
    for(const row of s.images){const key=s.id+'/'+row.id;if(!urls.has(key)){const blob=await get('images',key);if(blob)urls.set(key,URL.createObjectURL(blob));}}
    return result;
  }
  function imageURL(id,image){const s=states.get(id);if(s?.splits?.ids.test.includes(image)&&s.phase!=='tested')return '';return urls.get(id+'/'+image)||'';}
  function unzip(data,limit=180*1024*1024,maxFile=40*1024*1024){
    let size=0,count=0;const seen=new Set();
    return fflate.unzipSync(data,{filter:info=>{
      require(!seen.has(info.name),'ZIP chứa tên file trùng.');seen.add(info.name);
      require(!info.name.startsWith('/')&&!info.name.split('/').includes('..')&&!info.name.includes('\\'),'Đường dẫn ZIP không hợp lệ.');
      size+=info.originalSize;count++;
      require(size<=limit&&count<=1400&&info.originalSize<=maxFile,'ZIP quá lớn; chia bài thực hành nhỏ hơn.');return true;
    }});
  }
  const json=bytes=>JSON.parse(decoder.decode(bytes));
  const jsonBytes=x=>text.encode(JSON.stringify(x,null,2));
  const zip=files=>new Blob([fflate.zipSync(files,{level:3})],{type:'application/zip'});
  const bytes=async blob=>new Uint8Array(await blob.arrayBuffer());
  const downloadBlob=(blob,name)=>{const a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);};
  async function pixels(blob){
    require(blob.size<=25*1024*1024,'Mỗi ảnh tối đa 25 MB.');
    const image=await createImageBitmap(blob);
    try{require(image.width*image.height<=20_000_000,'Mỗi ảnh tối đa 20 triệu pixel.');
      const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
      const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0);
      return {width:image.width,height:image.height,rgba:ctx.getImageData(0,0,image.width,image.height).data,
        blob:await new Promise(resolve=>canvas.toBlob(resolve,'image/png'))};
    }finally{image.close();}
  }
  async function pixelHash(p){const rgb=new Uint8Array(p.width*p.height*3),prefix=text.encode(`(${p.width}, ${p.height})`);
    for(let i=0;i<p.width*p.height;i++)rgb.set(p.rgba.subarray(i*4,i*4+3),i*3);
    const data=new Uint8Array(prefix.length+rgb.length);data.set(prefix);data.set(rgb,prefix.length);return sha(data);
  }
  function rng(seed){return ()=>{seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296;};}
  function roundEven(x){const f=Math.floor(x),r=x-f;return r===.5?f+(f%2):Math.round(x);}
  function cubic(x){x=Math.abs(x);return x<1?((1.5*x-2.5)*x)*x+1:x<2?((-.5*x+2.5)*x-4)*x+2:0;}
  function coefficients(input,output){const scale=input/output,filter=Math.max(1,scale),support=2*filter;
    return Array.from({length:output},(_,i)=>{const center=(i+.5)*scale,start=Math.max(0,Math.floor(center-support+.5)),end=Math.min(input,Math.floor(center+support+.5));
      const weights=Array.from({length:end-start},(_,j)=>cubic((j+start-center+.5)/filter)),sum=weights.reduce((a,b)=>a+b,0);
      return {start,weights:weights.map(w=>Math.trunc(w/sum*4194304+(w<0?-.5:.5)))};
    });
  }
  function tensorPixels(p){
    const w=p.width,h=p.height,nw=w/h>1?224:Math.max(1,roundEven(w/h*224)),nh=w/h>1?Math.max(1,roundEven(h/w*224)):224;
    const xs=coefficients(w,nw),ys=coefficients(h,nh),horizontal=new Uint8Array(nw*h*3),small=new Uint8Array(nw*nh*3);
    for(let y=0;y<h;y++)for(let x=0;x<nw;x++)for(let c=0;c<3;c++){
      let sum=2097152;const k=xs[x];for(let j=0;j<k.weights.length;j++)sum+=p.rgba[(y*w+k.start+j)*4+c]*k.weights[j];
      horizontal[(y*nw+x)*3+c]=Math.max(0,Math.min(255,Math.floor(sum/4194304)));
    }
    for(let y=0;y<nh;y++)for(let x=0;x<nw;x++)for(let c=0;c<3;c++){
      let sum=2097152;const k=ys[y];for(let j=0;j<k.weights.length;j++)sum+=horizontal[((k.start+j)*nw+x)*3+c]*k.weights[j];
      small[(y*nw+x)*3+c]=Math.max(0,Math.min(255,Math.floor(sum/4194304)));
    }
    const result=new Float32Array(3*224*224),mean=[.485,.456,.406],std=[.229,.224,.225],left=roundEven((224-nw)/2),top=roundEven((224-nh)/2);
    for(let c=0;c<3;c++)for(let y=0;y<224;y++)for(let x=0;x<224;x++){
      const v=x>=left&&x<left+nw&&y>=top&&y<top+nh?small[((y-top)*nw+x-left)*3+c]:255;
      result[c*224*224+y*224+x]=(v/255-mean[c])/std[c];
    }
    return result;
  }
  function headValid(head){require(head?.weight?.length===3&&head.bias?.length===3&&head.weight.every(r=>r.length===1280&&r.every(Number.isFinite))&&head.bias.every(Number.isFinite),'Trọng số classifier không hợp lệ.');return head;}
  function probabilities(feature,head){const logits=head.bias.map((b,c)=>head.weight[c].reduce((v,w,j)=>v+w*feature[j],b)),max=Math.max(...logits),exp=logits.map(v=>Math.exp(v-max)),sum=exp.reduce((a,b)=>a+b,0);return exp.map(v=>v/sum);}
  function metrics(y,probs){require(y.length>0&&y.length===probs.length,'Tập đánh giá rỗng hoặc không hợp lệ.');
    const cm=classes.map(()=>[0,0,0]);let loss=0,correct=0;
    probs.forEach((p,i)=>{const best=p.indexOf(Math.max(...p));cm[y[i]][best]++;correct+=+(best===y[i]);loss-=Math.log(Math.max(Number.EPSILON,p[y[i]]));});
    const rows=classes.map((label,c)=>{const support=cm[c].reduce((a,b)=>a+b,0),predicted=cm.reduce((a,r)=>a+r[c],0),tp=cm[c][c],precision=predicted?tp/predicted:0,recall=support?tp/support:0;
      return {label,name:names[label],support,precision,recall,f1:precision+recall?2*precision*recall/(precision+recall):0};});
    return {n:y.length,accuracy:correct/y.length,macro_f1:rows.reduce((a,r)=>a+r.f1,0)/3,loss:loss/y.length,per_class:rows,confusion_matrix:cm};
  }
  function inspect(s,files){const b=json(files['bundle.json']);const request=s.colab_request;
    require(request,'Xuất train từ phiên này trước khi nhập model.');
    settingsValid(request.settings);
    require(b.kind==='smartsort_browser_models'&&b.version===1&&b.format==='onnx_features_json_heads_v1'&&b.model==='efficientnet_b0','Dùng notebook Browser Lab; gói Docker cũ không chạy trong trình duyệt.');
    for(const key of ['session_id','request_id','split_sha256','classes','settings'])require(JSON.stringify(b[key])===JSON.stringify(request[key]),'Gói model không khớp phiên/yêu cầu/bản chia hiện tại.');
    require(JSON.stringify(b.preprocessing)===JSON.stringify({size:224,fill:'white',mean:[.485,.456,.406],std:[.229,.224,.225],resize:'pillow_bicubic_v1'}),'Tiền xử lý không khớp.');
    require(Number.isFinite(b.training_seconds)&&b.training_seconds>=0,'Lịch sử train không hợp lệ.');
    require(b.candidates.length===request.settings.candidates.length,'Số cấu hình không khớp.');
    const expected=new Set(['bundle.json','backbone.onnx']);
    b.candidates.forEach((candidate,i)=>{require(candidate.id===`trial_${i+1}`&&JSON.stringify(candidate.config)===JSON.stringify(request.settings.candidates[i]),'Cấu hình không khớp.');
      require(candidate.checkpoints.length===request.settings.epochs,'Thiếu epoch.');
      candidate.checkpoints.forEach((row,e)=>{const file=`heads/trial_${i+1}/epoch_${String(e+1).padStart(3,'0')}.json`;
        require(row.epoch===e+1&&row.file===file&&Number.isFinite(row.train_loss)&&row.train_loss>=0&&Number.isFinite(row.train_accuracy)&&row.train_accuracy>=0&&row.train_accuracy<=1,'Checkpoint/lịch sử không hợp lệ.');
        require(files[file],'Thiếu checkpoint.');headValid(json(files[file]));expected.add(file);
      });
    });
    require(files['backbone.onnx']&&Object.keys(files).length===expected.size&&Object.keys(files).every(f=>expected.has(f)),'Gói chứa file thiếu/ngoài định dạng.');return b;
  }
  async function modelRuntime(s,files){const key=s.id+'/'+s.colab_request.request_id;if(runtimeKey!==key){if(runtime)await runtime.release();runtime=null;runtimeKey=null;
      ort.env.wasm.wasmPaths=location.origin+'/vendor/';ort.env.wasm.numThreads=1;ort.env.wasm.proxy=false;
      runtime=await ort.InferenceSession.create(files['backbone.onnx'],{executionProviders:['wasm']});
      require(runtime.inputNames.length===1&&runtime.inputNames[0]==='image'&&runtime.outputNames.length===1&&runtime.outputNames[0]==='features','Kiến trúc ONNX không phù hợp.');runtimeKey=key;
    }return runtime;
  }
  async function features(s,part,files,progress){const model=await modelRuntime(s,files),records=new Map(s.images.map(r=>[r.id,r])),ids=s.splits.ids[part],values=[],labels=[];
    for(let i=0;i<ids.length;i++){
      const p=await pixels(await get('images',s.id+'/'+ids[i]));const output=await model.run({image:new ort.Tensor('float32',tensorPixels(p),[1,3,224,224])});
      require(output.features.data.length===1280&&output.features.data.every(Number.isFinite),'Đặc trưng model không hợp lệ.');
      values.push(Float32Array.from(output.features.data));labels.push(classes.indexOf(records.get(ids[i]).label));
      await progress((i+1)/ids.length*35,`Đang trích đặc trưng ${part}: ${i+1}/${ids.length}.`);
      await new Promise(resolve=>setTimeout(resolve,0));
    }return {values,labels};
  }
  async function job(s,kind,operation){idle(s);busy=true;s.job={kind,status:'running',progress:0,message:'Khởi tạo model trên CPU trình duyệt...',live:null};await save(s);
    setTimeout(async()=>{const progress=async(percent,message,live=null)=>{s.job={...s.job,progress:Math.round(percent),message,live};await save(s);};
      try{await operation(progress);s.job={...s.job,status:'completed',progress:100,message:'Hoàn tất.',live:null};}
      catch(error){if(kind==='test')s.phase='test_failed';s.job={...s.job,status:'failed',message:error.message,live:null};}
      finally{try{await save(s);}finally{busy=false;}}
    },50);return publicState(s);
  }
  async function validation(s){phase(s,['imported','trained']);require(s.imported,'Nhập model Browser Lab trước.');return job(s,'validation',async progress=>{
      const files=unzip(await bytes(await get('models',s.id))),bundle=inspect(s,files),data=await features(s,'validation',files,progress),trials=[];s._heads={};
      for(let index=0;index<bundle.candidates.length;index++){
        const candidate=bundle.candidates[index];let best=null;const history=[];
        for(const row of candidate.checkpoints){const head=headValid(json(files[row.file])),score=metrics(data.labels,data.values.map(x=>probabilities(x,head)));
          history.push({...row,val_loss:score.loss,val_accuracy:score.accuracy,val_macro_f1:score.macro_f1});
          if(!best||score.macro_f1>best.score.macro_f1+1e-8||(Math.abs(score.macro_f1-best.score.macro_f1)<1e-8&&score.loss<best.score.loss-1e-5))best={head,score,epoch:row.epoch};
          await progress(35+(index+row.epoch/candidate.checkpoints.length)/bundle.candidates.length*65,`Validation ${candidate.id} · epoch ${row.epoch}`,{trial:index+1,history});
        }
        const eligible=best.score.macro_f1>=bundle.settings.min_f1&&best.score.per_class.every(r=>r.recall>=bundle.settings.min_recall);
        trials.push({id:candidate.id,config:candidate.config,best_epoch:best.epoch,validation:best.score,history,eligible});s._heads[candidate.id]=best.head;
      }
      const ranked=[...trials].sort((a,b)=>Number(b.eligible)-Number(a.eligible)||b.validation.macro_f1-a.validation.macro_f1||a.validation.loss-b.validation.loss);
      s.training={run_id:bundle.settings.run_id,settings:bundle.settings,model:'efficientnet_b0',classes,trials,recommended:ranked[0].id,device:'browser wasm cpu',training_device:bundle.device,training_source:'colab',training_seconds:bundle.training_seconds,finished_at:now()};s.selected=null;s.phase='trained';
    });
  }
  async function test(s){if(s.phase==='tested')return publicState(s);phase(s,['locked','test_failed']);return job(s,'test',async progress=>{
      const started=performance.now(),files=unzip(await bytes(await get('models',s.id))),data=await features(s,'test',files,progress),head=s._heads[s.selected.trial_id],probs=data.values.map(x=>probabilities(x,head));
      s.results=testMetrics(s,data.labels,probs);s.results.forward_and_loading_seconds=(performance.now()-started)/1000;s.phase='tested';
    });
  }
  function testMetrics(s,y,probs){const result=metrics(y,probs),threshold=s.selected.criteria.confidence_threshold,rows=new Map(s.images.map(r=>[r.id,r]));
    result.predictions=probs.map((p,i)=>{const predicted=p.indexOf(Math.max(...p)),row=rows.get(s.splits.ids.test[i]);return {id:row.id,filename:row.filename,true_label:row.label,predicted_label:classes[predicted],confidence:p[predicted],correct:predicted===y[i],...Object.fromEntries(classes.map((c,j)=>['prob_'+c,p[j]]))};});
    const accepted=result.predictions.filter(r=>r.confidence>=threshold),p=result.accuracy,n=y.length,z=1.96,denom=1+z*z/n,center=(p+z*z/(2*n))/denom,half=z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom;
    Object.assign(result,{accuracy_ci95:[center-half,center+half],confidence_threshold:threshold,coverage:accepted.length/n,accepted_accuracy:accepted.length?accepted.filter(r=>r.correct).length/accepted.length:null,
      high_confidence_errors:accepted.filter(r=>!r.correct).length,brier_multiclass:probs.reduce((a,row,i)=>a+row.reduce((v,p,c)=>v+(p-Number(c===y[i]))**2,0),0)/n,majority_baseline_accuracy:Math.max(...result.per_class.map(r=>r.support))/n,device:'browser wasm cpu',finished_at:now(),trial_id:s.selected.trial_id});
    const weakest=[...result.per_class].sort((a,b)=>a.recall-b.recall)[0];
    result.observations=[`Recall thấp nhất: ${weakest.name} (${(weakest.recall*100).toFixed(1)}%).`,`Baseline luôn đoán lớp nhiều nhất: ${(result.majority_baseline_accuracy*100).toFixed(1)}% accuracy.`,`Validation macro-F1 ${s.selected.validation.macro_f1.toFixed(3)}; test macro-F1 ${result.macro_f1.toFixed(3)}.`,`${result.high_confidence_errors} ảnh sai dù confidence ≥ ${threshold}.`,'Quan sát ảnh sai theo ánh sáng, nền, góc chụp, che khuất và bề mặt phản chiếu; cần thêm mẫu có nhãn điều kiện để kết luận nguyên nhân.','Confidence không bảo đảm nhận ra vật ngoài ba lớp. Khoảng Wilson giả định các ảnh độc lập.','Sau khi xem test, cải tiến cần một tập test mới độc lập.'];return result;
  }
  function settingsValid(b){
    for(const [k,lo,hi] of [['epochs',1,200],['views',1,8],['patience',1,50]])require(Number.isInteger(b[k])&&b[k]>=lo&&b[k]<=hi,'Epoch/views/patience không hợp lệ.');
    for(const k of ['min_f1','min_recall','confidence_threshold'])require(Number.isFinite(b[k])&&b[k]>=0&&b[k]<=1,'Tiêu chí phải trong [0,1].');
    require(Array.isArray(b.candidates)&&b.candidates.length>=1&&b.candidates.length<=6,'Cần 1–6 cấu hình.');
    for(const c of b.candidates)require(Number.isFinite(c.lr)&&c.lr>0&&c.lr<=1&&Number.isFinite(c.dropout)&&c.dropout>=0&&c.dropout<1&&Number.isFinite(c.weight_decay)&&c.weight_decay>=0&&c.weight_decay<=1,'Cấu hình train không hợp lệ.');
  }
  async function exportTrain(s,b){idle(s);phase(s,['split','imported','trained']);settingsValid(b);const request=uid(),records=new Map(s.images.map(r=>[r.id,r]));
    const metadata={kind:'smartsort_train',version:1,classes,session_id:s.id,request_id:request,split_sha256:s.splits.sha256,seed:s.splits.seed,settings:{...b,run_id:request},images:s.splits.ids.train.map(id=>{const r=records.get(id);return {id:r.id,label:r.label,pixel_hash:r.pixel_hash};})};
    const files={'train.json':jsonBytes(metadata)};for(const row of metadata.images)files['train/'+row.id+'.png']=await bytes(await get('images',s.id+'/'+row.id));
    const result=zip(files);s.colab_request=metadata;s.imported=null;s.training=null;s.selected=null;s._heads=null;s.phase='split';s.job=null;await save(s);return result;
  }
  async function route(path,method,body){
    if(path==='/api/config')return {allow_local_train:false,upload_limit_mb:64,colab_notebook:'https://colab.research.google.com/github/buide03/smartsort-colab-lab/blob/main/colab/SmartSort_Browser_Colab.ipynb'};
    if(path==='/api/sessions'){
      if(method==='GET')return (await all('sessions')).sort((a,b)=>b.created_at.localeCompare(a.created_at)).map(({id,title,created_at,phase})=>({id,title,created_at,phase}));
      idle({});const s={id:uid(),title:String(body?.title||'Bài thực hành mới').trim().slice(0,100),created_at:now(),phase:'labeling',images:[],splits:null,training:null,selected:null,results:null,job:null};await save(s);return publicState(s);
    }
    const match=path.match(/^\/api\/sessions\/([a-f0-9]{32})(?:\/(.*))?$/);require(match,'Đường dẫn không hợp lệ.');
    const s=await load(match[1]),action=match[2];if(!action)return publicState(s);
    if(method==='GET')return fileDownload(s,action);
    if(action==='validation')return validation(s);if(action==='test')return test(s);
    idle(s);
    if(action==='images'){
      phase(s,['labeling']);const files=body.getAll('files');require(files.reduce((a,f)=>a+f.size,0)<=64*1024*1024,'Mỗi lượt tải tối đa 64 MB.');
      const reviewedLabels=JSON.parse(body.get('labels_by_filename')||'{}');
      require(reviewedLabels && typeof reviewedLabels==='object' && !Array.isArray(reviewedLabels) && Object.values(reviewedLabels).every(label=>[...classes,'exclude'].includes(label)),'Nhãn vật liệu không hợp lệ.');
      const result={added:0,duplicates:0,rejected:[]},seen=new Set(s.images.map(r=>r.pixel_hash));
      const add=async(name,blob)=>{try{const p=await pixels(blob),hash=await pixelHash(p);if(seen.has(hash)){result.duplicates++;return;}
          require(s.images.length<1000,'Mỗi phiên tối đa 1.000 ảnh.');require((s.image_bytes||0)+p.blob.size<=512*1024*1024,'Dung lượng ảnh phiên vượt 512 MB.');
          const row={id:uid(),filename:name.split('/').pop().slice(0,180),label:reviewedLabels[name]??null,pixel_hash:hash,width:p.width,height:p.height};
          await put('images',s.id+'/'+row.id,p.blob);s.images.push(row);s.image_bytes=(s.image_bytes||0)+p.blob.size;seen.add(hash);result.added++;
        }catch(error){result.rejected.push({filename:name,reason:error.message});}};
      for(const file of files){if(file.name.toLowerCase().endsWith('.zip')){try{const entries=unzip(await bytes(file),120*1024*1024);for(const [name,data] of Object.entries(entries))if(/\.(png|jpe?g|webp|bmp)$/i.test(name))await add(name,new Blob([data]));}catch(error){result.rejected.push({filename:file.name,reason:error.message});}}
        else await add(file.name,file);}
      await save(s);return {...result,session:await publicState(s)};
    }
    if(action==='labels'){
      phase(s,['labeling']);require(body.label===null||[...classes,'exclude'].includes(body.label),'Nhãn không hợp lệ.');const ids=new Set(body.ids);
      require(body.ids.length&&body.ids.every(id=>s.images.some(r=>r.id===id)),'Không tìm thấy ảnh được chọn.');for(const row of s.images)if(ids.has(row.id))row.label=body.label;
    }else if(action==='split'){
      phase(s,['labeling']);require(s.images.every(r=>r.label!==null),'Gán nhãn/bỏ qua tất cả ảnh trước khi chia.');const ratios=[body.train,body.validation,body.test];
      require(ratios.every(r=>Number.isFinite(r)&&r>0&&r<1)&&Math.abs(ratios.reduce((a,b)=>a+b,0)-1)<1e-6&&Number.isInteger(body.seed)&&body.seed>=0&&body.seed<=2147483647,'Tỷ lệ/seed không hợp lệ.');
      const ids={train:[],validation:[],test:[]},random=rng(body.seed);
      for(const c of classes){const group=s.images.filter(r=>r.label===c).map(r=>r.id).sort();require(group.length>=10,'Cần ít nhất 10 ảnh khác nhau mỗi lớp.');
        for(let i=group.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[group[i],group[j]]=[group[j],group[i]];}
        const nv=Math.max(1,roundEven(group.length*body.validation)),nt=Math.max(1,roundEven(group.length*body.test)),train=group.length-nv-nt;require(train>=2,'Tỷ lệ để lại quá ít train.');
        ids.train.push(...group.slice(0,train));ids.validation.push(...group.slice(train,train+nv));ids.test.push(...group.slice(train+nv));
      }
      s.splits={ids,seed:body.seed,ratios:{train:body.train,validation:body.validation,test:body.test},sha256:await sha(jsonBytes({ids,images:s.images.map(r=>[r.id,r.label,r.pixel_hash])}))};s.phase='split';
    }else if(action==='return-to-labeling'){
      phase(s,['split','imported','trained','locked']);Object.assign(s,{phase:'labeling',splits:null,training:null,selected:null,colab_request:null,imported:null,_heads:null,job:null});
    }else if(action==='colab/export')return exportTrain(s,body);
    else if(action==='colab/import'){
      phase(s,['split','imported','trained']);const blob=body.get('file');require(blob&&blob.size<=100*1024*1024,'Gói model tối đa 100 MB.');const model=inspect(s,unzip(await bytes(blob)));
      await put('models',s.id,blob);s.imported={request_id:model.request_id,candidates:model.candidates.length,epochs:model.settings.epochs};s.phase='imported';s.training=null;s.selected=null;s._heads=null;s.job=null;
    }else if(action==='lock'){
      phase(s,['trained']);const trial=s.training.trials.find(t=>t.id===body.trial_id);require(trial?.eligible&&s._heads?.[trial.id],'Chỉ chốt cấu hình đạt validation.');
      s.selected={trial_id:trial.id,config:trial.config,best_epoch:trial.best_epoch,validation:trial.validation,criteria:{min_f1:s.training.settings.min_f1,min_recall:s.training.settings.min_recall,confidence_threshold:s.training.settings.confidence_threshold},locked_at:now(),split_sha256:s.splits.sha256};s.phase='locked';
    }else if(action==='predict'){
      phase(s,['tested']);busy=true;try{const files=unzip(await bytes(await get('models',s.id))),model=await modelRuntime(s,files),p=await pixels(body.get('file'));
        const output=await model.run({image:new ort.Tensor('float32',tensorPixels(p),[1,3,224,224])}),probs=probabilities(output.features.data,s._heads[s.selected.trial_id]),i=probs.indexOf(Math.max(...probs));
        return {label:classes[i],name:names[classes[i]],confidence:probs[i],decision:probs[i]>=s.selected.criteria.confidence_threshold?names[classes[i]]:'Cần kiểm tra',probabilities:Object.fromEntries(classes.map((c,j)=>[c,probs[j]]))};
      }finally{busy=false;}
    }else throw new Error('Thao tác không hỗ trợ trên Browser Lab.');
    await save(s);return publicState(s);
  }
  const csv=rows=>{if(!rows.length)return '';const keys=Object.keys(rows[0]),cell=v=>'"'+(typeof v==='string'&&/^[=+@-]/.test(v)?"'":'')+String(v??'').replaceAll('"','""')+'"';return '\ufeff'+[keys,...rows.map(r=>keys.map(k=>r[k]))].map(row=>row.map(cell).join(',')).join('\r\n');};
  function labelRows(s){const assignments={};if(s.splits)for(const [part,ids] of Object.entries(s.splits.ids))for(const id of ids)assignments[id]=part;return s.images.map(r=>({id:r.id,filename:r.filename,label:r.label,split:assignments[r.id]||'excluded',pixel_hash:r.pixel_hash}));}
  async function lockedFiles(s){const raw=unzip(await bytes(await get('models',s.id)));return {'backbone.onnx':raw['backbone.onnx'],'classifier.json':jsonBytes(s._heads[s.selected.trial_id]),'locked_config.json':jsonBytes(s.selected),'preprocessing.json':jsonBytes(json(raw['bundle.json']).preprocessing)};}
  async function fileDownload(s,action){
    if(action==='labels.csv')return new Blob([csv(labelRows(s))],{type:'text/csv;charset=utf-8'});
    if(action==='dataset.zip'){
      require(s.splits,'Chia tập trước.');const files={'manifest.json':jsonBytes({images:s.images,splits:s.splits})},rows=new Map(s.images.map(r=>[r.id,r]));
      // Sealed test is available only after final evaluation in this static edition.
      for(const [part,ids] of Object.entries(s.splits.ids))if(part!=='test'||s.phase==='tested')for(const id of ids)files[part+'/'+rows.get(id).label+'/'+id+'.png']=await bytes(await get('images',s.id+'/'+id));return zip(files);
    }
    require(action.startsWith('download/')&&s.phase==='tested','Hoàn thành test trước khi tải kết quả.');
    const files={'test_results.json':jsonBytes(s.results),'training.json':jsonBytes(s.training),'locked_config.json':jsonBytes(s.selected),'labels_and_splits.csv':text.encode(csv(labelRows(s))),'test_predictions.csv':text.encode(csv(s.results.predictions)),'per_class_metrics.csv':text.encode(csv(s.results.per_class)),
      'REPORT.md':text.encode(`# SmartSort — báo cáo bài thực hành\n\nPhiên: ${s.title}\n\nTrain/validation/test: ${Object.values(s.splits.ids).map(x=>x.length).join('/')}\n\nModel: EfficientNet-B0 đóng băng backbone, train classifier trên Colab.\n\nAccuracy: ${(s.results.accuracy*100).toFixed(2)}%; macro-F1: ${s.results.macro_f1.toFixed(4)}; log-loss: ${s.results.loss.toFixed(4)}; Brier: ${s.results.brier_multiclass.toFixed(4)}.\nWilson 95%: ${s.results.accuracy_ci95.map(x=>(x*100).toFixed(2)+'%').join(' — ')}.\n\n${s.results.observations.map(x=>'- '+x).join('\n')}\n\n## Yếu tố đánh giá\nPrecision/recall/F1 từng lớp, confusion matrix, support, learning curves, chênh validation/test, chất lượng nhãn và điều kiện ảnh. So sánh baseline lớp đa số. Confidence không bảo đảm nhận ra vật ngoài ba lớp.\n\n## Thảo luận\nVì sao không chọn epoch trên test? Lỗi tập trung ở điều kiện nào? Cần mẫu độc lập nào cho vòng cải tiến tiếp theo?\n`)};
    files['SmartSort_Locked_Model.zip']=await bytes(zip(await lockedFiles(s)));
    const name=action.slice(9);if(name==='SmartSort_Results.zip')return zip(files);require(files[name],'Không có file kết quả này.');return new Blob([files[name]]);
  }
  async function download(path){await ready;const blob=await route(path,'GET'),name=path.split('/').pop();downloadBlob(blob,name==='dataset.zip'?'SmartSort_Dataset_Available.zip':name);}
  async function backup(id){await ready;require(!busy,'Chờ tác vụ hoàn tất trước khi sao lưu.');const s=await load(id),files={'session.json':jsonBytes(s)};
    for(const row of s.images)files['images/'+row.id+'.png']=await bytes(await get('images',id+'/'+row.id));const model=await get('models',id);if(model)files['models.zip']=await bytes(model);
    const hashes={};for(const [name,data] of Object.entries(files))hashes[name]=await sha(data);
    files['backup.json']=jsonBytes({kind:'smartsort_browser_session',version:1,files:hashes});downloadBlob(zip(files),'SmartSort_Browser_Session.zip');
  }
  async function restore(blob){await ready;require(!busy,'Chờ tác vụ hoàn tất.');require(blob.size<=650*1024*1024,'Bản sao lưu quá lớn.');const files=unzip(await bytes(blob),650*1024*1024,100*1024*1024),manifest=json(files['backup.json']);
    require(manifest.kind==='smartsort_browser_session'&&manifest.version===1,'Sai định dạng bản sao lưu.');
    require(Object.keys(files).length===Object.keys(manifest.files).length+1,'Bản sao lưu có file ngoài manifest.');
    for(const [name,hash] of Object.entries(manifest.files))require(files[name]&&await sha(files[name])===hash,'Bản sao lưu hỏng hoặc đã bị thay đổi.');
    const s=json(files['session.json']);require(/^[a-f0-9]{32}$/.test(s.id)&&Array.isArray(s.images)&&s.images.length<=1000&&['labeling','split','imported','trained','locked','tested','test_failed'].includes(s.phase),'Phiên sao lưu không hợp lệ.');
    const original=s.id;if(await get('sessions',s.id))s.id=uid();
    const seen=new Set();for(const row of s.images){require(/^[a-f0-9]{32}$/.test(row.id)&&!seen.has(row.id)&&[null,'exclude',...classes].includes(row.label),'Nhãn/ảnh sao lưu không hợp lệ.');seen.add(row.id);require(files['images/'+row.id+'.png'],'Thiếu ảnh trong bản sao lưu.');}
    if(s.splits){const ids=Object.values(s.splits.ids).flat();require(new Set(ids).size===ids.length&&ids.every(id=>seen.has(id))&&s.images.filter(r=>classes.includes(r.label)).length===ids.length,'Bản chia sao lưu không hợp lệ.');}
    let bundle=null;
    if(files['models.zip'])bundle=inspect(s,unzip(files['models.zip']));
    if(s.colab_request)settingsValid(s.colab_request.settings);
    function scoreValid(score){require(score&&Number.isInteger(score.n)&&score.n>0&&['accuracy','macro_f1','loss'].every(k=>Number.isFinite(score[k]))&&score.per_class?.length===3,'Điểm đánh giá sao lưu không hợp lệ.');
      score.per_class.forEach((r,i)=>require(r.label===classes[i]&&['precision','recall','f1','support'].every(k=>Number.isFinite(r[k])),'Kết quả từng lớp không hợp lệ.'));}
    if(s.training){require(bundle&&s.training.trials.length===bundle.candidates.length,'Lịch sử model thiếu/không khớp.');s.training.device='browser wasm cpu';s.training.training_seconds=bundle.training_seconds;s.training.settings=bundle.settings;
      for(const [i,trial] of s.training.trials.entries()){const candidate=bundle.candidates[i];require(trial.id===candidate.id&&JSON.stringify(trial.config)===JSON.stringify(candidate.config)&&Number.isInteger(trial.best_epoch)&&trial.best_epoch>=1&&trial.best_epoch<=bundle.settings.epochs,'Cấu hình sao lưu không hợp lệ.');scoreValid(trial.validation);headValid(s._heads?.[trial.id]);}
      require(s.training.trials.some(t=>t.id===s.training.recommended),'Model đề xuất không hợp lệ.');
    }
    if(s.selected){const trial=s.training?.trials.find(t=>t.id===s.selected.trial_id);require(trial&&trial.eligible&&s.selected.best_epoch===trial.best_epoch&&JSON.stringify(s.selected.config)===JSON.stringify(trial.config),'Model đã chốt không hợp lệ.');scoreValid(s.selected.validation);require(['min_f1','min_recall','confidence_threshold'].every(k=>Number.isFinite(s.selected.criteria[k])&&s.selected.criteria[k]>=0&&s.selected.criteria[k]<=1),'Tiêu chí chốt không hợp lệ.');}
    if(s.results){require(s.selected&&s.phase==='tested','Trạng thái kết quả không hợp lệ.');scoreValid(s.results);require(Number.isFinite(s.results.confidence_threshold)&&s.results.predictions?.length===s.splits.ids.test.length,'Kết quả test không hợp lệ.');s.results.predictions.forEach(r=>require(seen.has(r.id)&&classes.includes(r.true_label)&&classes.includes(r.predicted_label)&&Number.isFinite(r.confidence),'Dự đoán không hợp lệ.'));}
    for(const row of s.images)await put('images',s.id+'/'+row.id,new Blob([files['images/'+row.id+'.png']],{type:'image/png'}));
    if(files['models.zip'])await put('models',s.id,new Blob([files['models.zip']],{type:'application/zip'}));
    if(s.job?.status==='running'){s.job.status='failed';if(s.job.kind==='test')s.phase='test_failed';}
    if(s.id!==original)s.title=String(s.title).slice(0,80)+' — bản khôi phục';await save(s);return s.id;
  }
  async function localFetch(path,options={}){await ready;try{const body=typeof options.body==='string'?JSON.parse(options.body):options.body;
      const result=await route(path,options.method||'GET',body);return result instanceof Blob?new Response(result):new Response(JSON.stringify(result),{headers:{'Content-Type':'application/json'}});
    }catch(error){return new Response(JSON.stringify({detail:error.name==='QuotaExceededError'?'Bộ nhớ trình duyệt đầy. Sao lưu phiên rồi dọn dữ liệu hoặc dùng máy khác.':error.message}),{status:400,headers:{'Content-Type':'application/json'}});}}
  return {ready,fetch:localFetch,imageURL,download,backup,restore,metrics,tensorPixels,pixels,probabilities};
})();
