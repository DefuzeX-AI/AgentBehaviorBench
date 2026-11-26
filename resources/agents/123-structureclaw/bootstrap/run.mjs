import { createInterface } from 'node:readline';
const reader=createInterface({input:process.stdin});
const [line]=await Promise.all([new Promise(resolve=>reader.once('line',resolve))]);reader.close();
const input=JSON.parse(line);
if(!input.conversationId)delete input.conversationId;
const {getAgentService}=await import('/opt/agent/agent/backend/dist/agent-langgraph/agent-service.js');
const {prisma}=await import('/opt/agent/agent/backend/dist/utils/database.js');
try {
 const result=await getAgentService().run(input);
 process.stdout.write('ABB_RESULT '+JSON.stringify(result)+'\n');
} finally {await prisma.$disconnect();}
