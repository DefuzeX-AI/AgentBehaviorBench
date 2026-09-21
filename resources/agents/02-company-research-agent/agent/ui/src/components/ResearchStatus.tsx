import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
import type { ResearchStatusProps } from '../types';
import { fadeInAnimation } from '../styles';

const ResearchStatus = ({
  status,
  error,
  isComplete,
  currentPhase,
  isResetting,
  glassStyle,
  loaderColor,
  statusRef
}: ResearchStatusProps) => {
  if (!status) return null;

  return (
    <div 
      ref={statusRef} 
      className={`${glassStyle.base} rounded-2xl p-6 ${fadeInAnimation.fadeIn} ${isResetting ? 'opacity-0 transform -translate-y-4' : 'opacity-100 transform translate-y-0'} bg-white/80 backdrop-blur-sm border-gray-200 font-['DM_Sans']`}
    >
      <div className="flex items-center space-x-4">
        <div className="flex-shrink-0">
          {error ? (
            <div className={`${glassStyle.base} p-2 rounded-full bg-[#FE363B]/10 border-[#FE363B]/20`}>
              <XCircle className="h-5 w-5 text-[#FE363B]" />
            </div>
          ) : status?.step === "Complete" || isComplete ? (
            <div className={`${glassStyle.base} p-2 rounded-full bg-[#22C55E]/10 border-[#22C55E]/20`}>
              <CheckCircle2 className="h-5 w-5 text-[#22C55E]" />
            </div>
          ) : currentPhase === 'search' || currentPhase === 'enrichment' || (status?.step === "Processing" && status.message.includes("scraping")) ? (
            <div className={`${glassStyle.base} p-2 rounded-full bg-[#468BFF]/10 border-[#468BFF]/20`}>
              <Loader2 className="h-5 w-5 animate-spin loader-icon" style={{ stroke: loaderColor }} />
            </div>
          ) : currentPhase === 'briefing' ? (
            <div className={`${glassStyle.base} p-2 rounded-full bg-[#468BFF]/10 border-[#468BFF]/20`}>
              <Loader2 className="h-5 w-5 animate-spin loader-icon" style={{ stroke: loaderColor }} />
            </div>
          ) : (
            <div className={`${glassStyle.base} p-2 rounded-full bg-[#468BFF]/10 border-[#468BFF]/20`}>
              <Loader2 className="h-5 w-5 animate-spin loader-icon" style={{ stroke: loaderColor }} />
            </div>
          )}
        </div>
        <div className="flex-1">
          <p className="font-medium text-gray-900/90">{status.step}</p>
          <p className="text-sm text-gray-600 whitespace-pre-wrap">
            {error || status.message}
          </p>
        </div>
      </div>
    </div>
  );
};

export default ResearchStatus; 