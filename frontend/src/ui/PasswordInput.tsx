import { useState } from 'react';
import type { InputHTMLAttributes } from 'react';
import { Eye, EyeOff } from 'lucide-react';

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  visibilityLabel?: string;
};

export function PasswordInput({ visibilityLabel = 'password', ...props }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const actionLabel = visible ? `Hide ${visibilityLabel}` : `Show ${visibilityLabel}`;

  return (
    <div className="password-input">
      <input type={visible ? 'text' : 'password'} {...props} />
      <button
        type="button"
        className="password-input__toggle"
        aria-label={actionLabel}
        title={actionLabel}
        aria-pressed={visible}
        onClick={() => setVisible((current) => !current)}
      >
        {visible ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}
      </button>
    </div>
  );
}
