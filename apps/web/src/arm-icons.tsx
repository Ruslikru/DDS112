import React from 'react';

// Local vector artwork following the supplied operational ARM pictograms.
// Keep this set separate from the teaching and administration icons.
type Symbol='journal'|'screen'|'statistics'|'gear'|'document'|'help'|'people'|'helicopter'|'binoculars'|'control'|'shift'|'globe'|'exit'|'headset';
export function ArmIcon({name,size=24}:{name:Symbol,size?:number}){
 const line={fill:'none',stroke:'currentColor',strokeWidth:2,strokeLinecap:'round' as const,strokeLinejoin:'round' as const};
 const artwork:Record<Symbol,React.ReactNode>={
  journal:<><rect x="4" y="4" width="16" height="3" rx=".5"/><rect x="4" y="10.5" width="16" height="3" rx=".5"/><rect x="4" y="17" width="16" height="3" rx=".5"/></>,
  screen:<><path {...line} d="M19 13v7H4V4h9"/><path d="m8 14 9-10 3 3-9 10-4 1zM18 3l1-1a1 1 0 0 1 1.5 0L22 3.5a1 1 0 0 1 0 1.5l-1 1z"/></>,
  statistics:<><rect {...line} x="3" y="3" width="18" height="18" rx="1"/><path d="M6 12h3v6H6zm5-6h3v12h-3zm5 3h2v9h-2z"/></>,
  gear:<path fillRule="evenodd" d="m10 1 4 0 .7 3 2 .8 2.6-1.5 2.8 2.8-1.5 2.6.8 2 3 .7v4l-3 .7-.8 2 1.5 2.6-2.8 2.8-2.6-1.5-2 .8-.7 3h-4l-.7-3-2-.8-2.6 1.5L1.9 19l1.5-2.6-.8-2-3-.7v-4l3-.7.8-2L1.9 4.4l2.8-2.8L7.3 3l2-.8zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8" transform="translate(1 1) scale(.9)"/>,
  document:<><path fillRule="evenodd" d="M5 1h10l5 5v17H4V1zm9 2v5h5zm-7 8v2h10v-2zm0 4v2h10v-2zm0 4v2h8v-2z"/></>,
  help:<><circle {...line} cx="12" cy="12" r="9.5"/><path {...line} strokeWidth="2.6" d="M8.5 8.5a3.5 3.5 0 1 1 6 2.5L12 13v1"/><circle cx="12" cy="18" r="1.3"/></>,
  people:<><circle cx="9" cy="6" r="3.4"/><circle cx="17.5" cy="8" r="2.7"/><path d="M2 21v-5a7 7 0 0 1 14 0v5zm14-8a5.5 5.5 0 0 1 7 5v3h-5v-5a9 9 0 0 0-2-3"/></>,
  helicopter:<><path {...line} d="M3 3h18M12 3v4M6 21h14M10 18v3m7-3v3"/><path d="M8 8h7a5 5 0 0 1 5 5v4H9a5 5 0 0 1-5-5L0 9V7l7 3zm5 1 2 5h4a4 4 0 0 0-4-5z" fillRule="evenodd"/><path d="m20 12 3-5h1v9h-4z"/></>,
  binoculars:<><path {...line} d="m3 13 3-8h3l1 7m4 0 1-7h3l3 8M9 5V3h2m2 0h2v2M10 13h4"/><circle {...line} cx="6" cy="16" r="4.5"/><circle {...line} cx="18" cy="16" r="4.5"/></>,
  control:<><path {...line} d="M11 3H4v18h15v-7M7 8h3m-3 4h2m-2 4h4"/><path d="m11 13 9-10 3 3-9 10-4 1zM21 2l1-1 3 3-1 1z"/></>,
  shift:<><path fillRule="evenodd" d="M6 3h3V1h6v2h3v2h3v18H3V5h3zm3 1h6v2H9zm3 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm-5 12h10v-2a5 5 0 0 0-10 0z"/></>,
  globe:<><circle {...line} cx="12" cy="12" r="10"/><ellipse {...line} cx="12" cy="12" rx="4.5" ry="10"/><path {...line} d="M2 12h20M4 6.5h16M4 17.5h16"/></>,
  exit:<><circle cx="15.5" cy="3" r="2.2"/><path d="m12 6 4 1 2 4 4 1-.5 2-5-1-2-3-2 5 4 3v5h-2v-4l-4-2-2 6H6l3-9 2-5-3 2-2 4-2-1 2-5z"/><path {...line} strokeWidth="1.5" d="M5 2H1v19h4"/></>,
  headset:<><path {...line} d="M4 13V10a8 8 0 0 1 16 0v8a3 3 0 0 1-3 3h-3"/><rect {...line} x="2" y="11" width="4" height="8" rx="1.5"/><rect {...line} x="18" y="11" width="4" height="8" rx="1.5"/><rect x="10" y="20" width="5" height="2.5" rx="1"/></>,
 };
 return <svg className="arm-original-icon" width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">{artwork[name]}</svg>;
}
const glyph=(name:Symbol)=>({size=24}:{size?:number})=><ArmIcon name={name} size={size}/>;
export const ArmMenuIcons={journal:glyph('journal'),screen:glyph('screen'),statistics:glyph('statistics'),gear:glyph('gear'),document:glyph('document'),help:glyph('help'),people:glyph('people'),helicopter:glyph('helicopter'),binoculars:glyph('binoculars'),control:glyph('control'),shift:glyph('shift'),globe:glyph('globe')};
