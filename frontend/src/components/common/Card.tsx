import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  footer?: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  title,
  subtitle,
  action,
  footer,
}) => {
  return (
    <div
      className={`rounded-[var(--radius-lg)] border border-border bg-card text-card-foreground shadow-[var(--shadow-resting)] transition-all hover:shadow-[var(--shadow-raised)] ${className}`}
    >
      {(title || subtitle || action) && (
        <div className="flex items-center justify-between border-b border-border/70 px-5 py-4">
          <div>
            {title && <h3 className="font-heading text-base font-semibold tracking-tight text-foreground">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          {action && <div className="flex items-center gap-2">{action}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
      {footer && (
        <div className="border-t border-border/70 bg-muted/20 px-5 py-3 text-xs text-muted-foreground">
          {footer}
        </div>
      )}
    </div>
  );
};
