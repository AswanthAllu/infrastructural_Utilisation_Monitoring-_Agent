import React from 'react';

interface RemediationListProps {
  text?: string | null;
  className?: string;
}

/** Render remediation content as clear, one-by-one numbered actions. */
export const RemediationList: React.FC<RemediationListProps> = ({ text, className = '' }) => {
  if (!text?.trim()) return null;

  const items = text
    .split(/\r?\n|\s*;\s*/)
    .map((item) => item.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '').trim())
    .filter(Boolean);

  return (
    <ol className={`mt-1.5 list-decimal space-y-1.5 pl-5 text-xs text-foreground ${className}`}>
      {items.map((item, index) => (
        <li key={`${index}-${item}`} className="pl-1 leading-relaxed">{item}</li>
      ))}
    </ol>
  );
};

export default RemediationList;
