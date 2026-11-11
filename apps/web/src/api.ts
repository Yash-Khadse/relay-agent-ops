export class ApiError extends Error { constructor(public status:number,message:string){super(message);} }
export async function api<T>(path:string,body?:unknown):Promise<T>{
 const response=await fetch(`/api${path}`,{credentials:'include',headers:body?{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()}:undefined,method:body?'POST':'GET',body:body?JSON.stringify(body):undefined});
 if(!response.ok){const error=await response.json().catch(()=>({detail:response.statusText}));throw new ApiError(response.status,error.detail||'Request failed');}
 if(response.status===204)return undefined as T; return response.json();
}
export async function download(id:string,title:string){const response=await fetch(`/api/artifacts/${encodeURIComponent(id)}/download`,{credentials:'include'});if(!response.ok)throw new Error('Download unavailable');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=`${title.replace(/[^a-z0-9 -]/gi,'')}.md`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export interface Execution{id:string;template_id:string;topic:string;brief:string;status:string;current_node:string;created_at:string;updated_at:string;revision:number;mode:string;error?:string;approvals?:Approval[];artifacts?:Artifact[];ticket?:unknown}
export interface Approval{id:string;execution_id:string;topic:string;status:string;revision:number;draft:string;risk:unknown;created_at:string;expires_at:string;comment?:string}
export interface Artifact{id:string;execution_id:string;title:string;approved:boolean;producer:string;version:number;created_at:string;content_type:string;content_hash:string}
export interface Template{id:string;name:string;description:string;version:number;sample:{topic:string;brief:string};nodes:{id:string;label:string;agent:string;type:string}[];edges:{source:string;target:string;label?:string}[]}
export interface Source{id:string;title:string;content:string;kind:string}
export interface Agent{id:string;name:string;role:string;description:string;tools:string[];max_iterations:number;output_schema:unknown}
export interface Metrics{total:number;completed:number;failed:number;pending_approvals:number;average_duration_seconds:number|null;llm_calls:number;input_tokens:number;output_tokens:number;estimated_cost_usd:number|null;retries:number;by_template:{template_id:string;total:number;completed:number}[];daily:{date:string;total:number;completed:number;failed:number}[];node_latency:{node:string;average_ms:number}[]}
export interface Settings{provider:string;model:string;configured:boolean;crew_enabled:boolean;demo_mode:boolean;max_executions:number;version:string}
export interface Event{id:number;kind:string;node:string;agent:string;message:string;created_at:string;data:unknown}
export function mergeEvents(previous:Event[],incoming:Event[]){return [...new Map([...previous,...incoming].map(event=>[event.id,event])).values()].sort((a,b)=>a.id-b.id);}
