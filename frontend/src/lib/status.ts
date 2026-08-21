import { ApiError } from '../api/client';
import type { UserStatus } from '../types';

export type Message = {
  type: 'info' | 'success' | 'error';
  text: string;
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.status}: ${error.message}`;
  if (error instanceof Error) return error.message;
  return 'Unexpected error';
}

export function formatDate(value: string | null): string {
  if (!value) return '-';
  return new Date(value).toLocaleString();
}

export function formatCalendarDate(value: string | null): string {
  if (!value) return '-';
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return value;
  return new Date(year, month - 1, day).toLocaleDateString();
}

export function statusClass(status: UserStatus): string {
  return `pill pill--${status}`;
}

export function verifiedClass(verified: boolean): string {
  return verified ? 'pill pill--approved' : 'pill pill--pending';
}
