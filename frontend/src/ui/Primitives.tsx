import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ButtonHTMLAttributes, CSSProperties, HTMLAttributes, KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export function cx(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(' ');
}

type ButtonVariant = 'primary' | 'secondary' | 'success' | 'danger' | 'ghost';
type ButtonSize = 'default' | 'compact';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: LucideIcon;
};

export function Button({
  variant = 'primary',
  size = 'default',
  icon: Icon,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      className={cx('ui-button', `ui-button--${variant}`, size === 'compact' && 'ui-button--compact', className)}
      {...props}
    >
      {Icon ? <Icon aria-hidden="true" size={16} strokeWidth={2.2} /> : null}
      <span>{children}</span>
    </button>
  );
}

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  icon: LucideIcon;
  variant?: ButtonVariant;
};

export function IconButton({ label, icon: Icon, variant = 'ghost', className, ...props }: IconButtonProps) {
  return (
    <button
      type="button"
      className={cx('icon-button', `icon-button--${variant}`, className)}
      aria-label={label}
      title={label}
      {...props}
    >
      <Icon aria-hidden="true" size={17} strokeWidth={2.2} />
    </button>
  );
}

type PillTone = 'approved' | 'pending' | 'rejected' | 'role' | 'neutral' | 'info';

export function StatusPill({ tone = 'neutral', children, icon: Icon }: { tone?: PillTone; children: ReactNode; icon?: LucideIcon }) {
  return (
    <span className={cx('pill', `pill--${tone}`)}>
      {Icon ? <Icon aria-hidden="true" size={13} strokeWidth={2.3} /> : null}
      {children}
    </span>
  );
}

export function MessageBanner({ type, text }: { type: 'info' | 'success' | 'error'; text: string }) {
  return (
    <div className={cx('message', `message--${type}`)} role={type === 'error' ? 'alert' : 'status'}>
      {text}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon: Icon,
}: {
  title: string;
  description?: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="empty-state">
      {Icon ? <Icon aria-hidden="true" size={20} strokeWidth={2.1} /> : null}
      <div>
        <strong>{title}</strong>
        {description ? <p>{description}</p> : null}
      </div>
    </div>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="section-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="section-header__actions">{actions}</div> : null}
    </header>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="progress-bar" aria-label={label} aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100} role="progressbar">
      <span style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function DataTable({ children, className }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx('workspace-table', className)}>{children}</div>;
}

export type SelectOption = {
  value: string;
  label: string;
  description?: string;
  meta?: string;
  previewTitle?: string;
  previewDescription?: string;
  disabled?: boolean;
};

type SelectControlProps = {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  descriptionMode?: 'inline' | 'tooltip' | 'hidden';
  searchable?: boolean;
  searchPlaceholder?: string;
};

function nextEnabledIndex(options: SelectOption[], currentIndex: number, direction: 1 | -1) {
  if (options.length === 0) return -1;
  for (let step = 1; step <= options.length; step += 1) {
    const index = (currentIndex + step * direction + options.length) % options.length;
    if (!options[index].disabled) return index;
  }
  return -1;
}

type SelectMenuGeometry = {
  placement: 'top' | 'bottom';
  style: CSSProperties;
  previewStyle: CSSProperties;
};

export function SelectControl({
  value,
  options,
  onChange,
  ariaLabel,
  placeholder = 'Select an option',
  disabled = false,
  className,
  descriptionMode = 'inline',
  searchable = false,
  searchPlaceholder = 'Search options...',
}: SelectControlProps) {
  const menuId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const [previewStyle, setPreviewStyle] = useState<CSSProperties>({});
  const [menuPlacement, setMenuPlacement] = useState<'top' | 'bottom'>('bottom');
  const selectedOption = options.find((option) => option.value === value);
  const visibleOptions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!searchable || !normalizedQuery) return options;
    return options.filter((option) => [
      option.label,
      option.value,
      option.description,
      option.meta,
      option.previewTitle,
      option.previewDescription,
    ].filter(Boolean).join(' ').toLowerCase().includes(normalizedQuery));
  }, [options, query, searchable]);
  const selectedVisibleIndex = visibleOptions.findIndex((option) => option.value === value);
  const firstEnabledIndex = visibleOptions.findIndex((option) => !option.disabled);
  const [activeIndex, setActiveIndex] = useState(-1);
  const activeOption = activeIndex >= 0 ? visibleOptions[activeIndex] : undefined;

  const computeMenuGeometry = (): SelectMenuGeometry | null => {
    const rect = rootRef.current?.getBoundingClientRect();
    if (!rect) return null;

    const gap = 7;
    const viewportMargin = 12;
    const spaceBelow = window.innerHeight - rect.bottom - gap - viewportMargin;
    const spaceAbove = rect.top - gap - viewportMargin;
    const shouldOpenBelow = spaceBelow >= 260 || spaceBelow >= spaceAbove;
    const availableSpace = Math.max(180, shouldOpenBelow ? spaceBelow : spaceAbove);
    const maxHeight = Math.min(className?.includes('select-control--paper') ? 340 : 360, availableSpace);
    const previewGap = 14;
    const previewWidth = Math.min(360, Math.max(220, window.innerWidth - rect.right - previewGap - viewportMargin));

    return {
      placement: shouldOpenBelow ? 'bottom' : 'top',
      style: {
        left: Math.round(rect.left),
        top: shouldOpenBelow ? Math.round(rect.bottom + gap) : undefined,
        bottom: shouldOpenBelow ? undefined : Math.round(window.innerHeight - rect.top + gap),
        width: Math.round(rect.width),
        maxHeight,
        minHeight: searchable ? Math.min(260, maxHeight) : undefined,
      },
      previewStyle: {
        left: Math.round(rect.right + previewGap),
        top: Math.round(rect.top),
        width: previewWidth,
      },
    };
  };

  const updateMenuGeometry = () => {
    const geometry = computeMenuGeometry();
    if (!geometry) return;
    setMenuPlacement(geometry.placement);
    setMenuStyle(geometry.style);
    setPreviewStyle(geometry.previewStyle);
  };

  const openMenu = () => {
    const geometry = computeMenuGeometry();
    if (geometry) {
      setMenuPlacement(geometry.placement);
      setMenuStyle(geometry.style);
      setPreviewStyle(geometry.previewStyle);
    }
    setOpen(true);
  };

  const closeMenu = () => setOpen(false);

  useEffect(() => {
    if (!open) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        closeMenu();
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [open]);

  useLayoutEffect(() => {
    if (!open) {
      setQuery('');
      setMenuStyle({});
      setPreviewStyle({});
      return;
    }
    updateMenuGeometry();
    window.addEventListener('resize', updateMenuGeometry);
    window.addEventListener('scroll', updateMenuGeometry, true);
    if (searchable) searchRef.current?.focus({ preventScroll: true });
    return () => {
      window.removeEventListener('resize', updateMenuGeometry);
      window.removeEventListener('scroll', updateMenuGeometry, true);
    };
  }, [className, open, searchable, visibleOptions.length]);

  useLayoutEffect(() => {
    if (open) {
      optionRefs.current[activeIndex]?.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIndex, open]);

  useEffect(() => {
    setActiveIndex(selectedVisibleIndex >= 0 ? selectedVisibleIndex : firstEnabledIndex);
  }, [firstEnabledIndex, query, selectedVisibleIndex, visibleOptions.length]);

  const chooseOption = (option: SelectOption | undefined) => {
    if (!option || option.disabled) return;
    onChange(option.value);
    closeMenu();
  };

  const moveActive = (direction: 1 | -1) => {
    setActiveIndex((current) => nextEnabledIndex(visibleOptions, current < 0 ? selectedVisibleIndex : current, direction));
  };

  const handleMenuKeyDown = (event: ReactKeyboardEvent<HTMLInputElement | HTMLButtonElement>) => {
    if (disabled) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      openMenu();
      moveActive(1);
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      openMenu();
      moveActive(-1);
    }
    if (event.key === 'Home') {
      event.preventDefault();
      openMenu();
      setActiveIndex(firstEnabledIndex);
    }
    if (event.key === 'End') {
      event.preventDefault();
      openMenu();
      const reversedIndex = [...visibleOptions].reverse().findIndex((option) => !option.disabled);
      setActiveIndex(reversedIndex < 0 ? -1 : visibleOptions.length - 1 - reversedIndex);
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      chooseOption(visibleOptions[activeIndex]);
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu();
    }
  };

  const handleButtonKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (searchable && event.key.length === 1 && event.key !== ' ' && !event.altKey && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      setQuery(event.key);
      openMenu();
      return;
    }
    if (event.key === ' ' || (event.key === 'Enter' && !open)) {
      event.preventDefault();
      openMenu();
      return;
    }
    handleMenuKeyDown(event);
  };

  const resolvedMenuStyle: CSSProperties = menuStyle.width ? menuStyle : { ...menuStyle, visibility: 'hidden' };
  const resolvedPreviewStyle: CSSProperties = previewStyle.width ? previewStyle : { ...previewStyle, visibility: 'hidden' };

  return (
    <div ref={rootRef} className={cx('select-control', `select-control--description-${descriptionMode}`, searchable && 'select-control--searchable', open && 'select-control--open', disabled && 'select-control--disabled', className)}>
      <button
        type="button"
        className="select-control__button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={menuId}
        disabled={disabled}
        onClick={() => { if (open) closeMenu(); else openMenu(); }}
        onKeyDown={handleButtonKeyDown}
      >
        <span className={cx('select-control__value', !selectedOption && 'select-control__value--placeholder')}>
          {selectedOption?.label ?? placeholder}
        </span>
        {selectedOption?.meta ? <span className="select-control__button-meta">{selectedOption.meta}</span> : null}
        <ChevronDown className="select-control__chevron" aria-hidden="true" size={16} strokeWidth={2.4} />
      </button>
      {open ? (
        <div
          className={cx('select-control__menu', `select-control__menu--${menuPlacement}`)}
          role="listbox"
          id={menuId}
          aria-label={ariaLabel}
          style={resolvedMenuStyle}
        >
          {searchable ? (
            <div className="select-control__search">
              <input
                ref={searchRef}
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleMenuKeyDown}
                placeholder={searchPlaceholder}
                aria-label={`Search ${ariaLabel.toLowerCase()}`}
              />
            </div>
          ) : null}
          {options.length === 0 ? <div className="select-control__empty">No options available</div> : null}
          {options.length > 0 && visibleOptions.length === 0 ? <div className="select-control__empty">No matching options</div> : null}
          {visibleOptions.map((option, index) => (
            <button
              key={option.value}
              ref={(element) => { optionRefs.current[index] = element; }}
              type="button"
              role="option"
              aria-selected={option.value === value}
              className={cx(
                'select-control__option',
                index === activeIndex && 'select-control__option--active',
                option.value === value && 'select-control__option--selected'
              )}
              disabled={option.disabled}
              title={descriptionMode === 'hidden' ? option.description : undefined}
              onMouseEnter={() => setActiveIndex(index)}
              onFocus={() => setActiveIndex(index)}
              onClick={() => chooseOption(option)}
            >
              <span className="select-control__option-main">
                <span>{option.label}</span>
                {option.meta ? <small>{option.meta}</small> : null}
              </span>
              {descriptionMode === 'inline' && option.description ? <span className="select-control__option-description">{option.description}</span> : null}
            </button>
          ))}
        </div>
      ) : null}
      {open && descriptionMode === 'tooltip' && activeOption ? (
        <div className="select-control__preview-card" aria-hidden="true" style={resolvedPreviewStyle}>
          <span>{activeOption.meta ?? activeOption.value}</span>
          <strong>{activeOption.previewTitle ?? activeOption.description ?? activeOption.label}</strong>
          {activeOption.previewDescription ? <small>{activeOption.previewDescription}</small> : null}
        </div>
      ) : null}
    </div>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}
