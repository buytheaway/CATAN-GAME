const{main}=require('./ocean-gpu.cjs'),{passes}=require('./readability-gpu.cjs');
const{startProportions,reference}=require('./proportions-demo.cjs'),h=require('./ocean-support.cjs');
const options={start:startProportions,reference,scenes:['base','new-shores-4','four-islands-4','fifty'],
 query:(...args)=>h.query(...args)+'&detail=pilot'};
const job=process.argv.includes('--passes')?passes(process.argv.at(-1),options):main(options);
job.catch(e=>{console.error(e);process.exitCode=1;});
