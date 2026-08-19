import { describe, it, expect } from 'vitest';
import { slugify, formatText, formatLastUpdated } from './utils.js';

// $ / getParams are thin DOM wrappers with no logic — not tested here.

describe('slugify', () => {
  it('lowercases and trims whitespace', () => {
    expect(slugify('  Hello World  ')).toBe('hello-world');
  });
  it('replaces spaces with hyphens', () => {
    expect(slugify('foo bar')).toBe('foo-bar');
  });
  it('replaces underscores with hyphens', () => {
    expect(slugify('foo_bar')).toBe('foo-bar');
  });
  it('strips special characters', () => {
    expect(slugify('C/GOTS!')).toBe('cgots');
  });
  it('collapses consecutive hyphens', () => {
    expect(slugify('a--b')).toBe('a-b');
  });
  it('strips leading and trailing hyphens', () => {
    expect(slugify('-hello-')).toBe('hello');
  });
  it('preserves dots and existing hyphens', () => {
    expect(slugify('v1.0-release')).toBe('v1.0-release');
  });
  it('returns empty string for empty input', () => {
    expect(slugify('')).toBe('');
  });
  it('returns empty string for null input', () => {
    expect(slugify(null)).toBe('');
  });
});

describe('formatText', () => {
  it('renders bold markdown', () => {
    expect(formatText('**bold**')).toContain('<strong>bold</strong>');
  });
  it('renders italic markdown', () => {
    expect(formatText('*italic*')).toContain('<em>italic</em>');
  });
  it('renders inline code', () => {
    expect(formatText('`code`')).toContain('<code>code</code>');
  });
  it('renders unordered list items', () => {
    expect(formatText('- item one')).toContain('<li>item one</li>');
  });
  it('wraps list items in a ul element', () => {
    expect(formatText('- item')).toContain('<ul>');
  });
  it('renders unchecked task list item', () => {
    const html = formatText('- [ ] todo');
    expect(html).toContain('type="checkbox"');
    expect(html).not.toContain('checked');
  });
  it('renders checked task list item', () => {
    expect(formatText('- [x] done')).toContain('checked');
  });
  it('converts newlines to br tags', () => {
    expect(formatText('line one\nline two')).toContain('<br>');
  });
});

describe('formatLastUpdated', () => {
  it('returns null for null input', () => {
    expect(formatLastUpdated(null)).toBeNull();
  });
  it('returns null for empty string', () => {
    expect(formatLastUpdated('')).toBeNull();
  });
  it('returns a formatted string for a UTC timestamp', () => {
    const result = formatLastUpdated('2026-04-15T14:30:00Z');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });
  it('returns a string matching DD MMM YY, HH:MM format', () => {
    const result = formatLastUpdated('2026-04-15T14:30:00Z');
    expect(result).toMatch(/^\d{2} [A-Z]{3} \d{2}, \d{2}:\d{2}/);
  });
  it('handles timestamps without a timezone suffix', () => {
    const result = formatLastUpdated('2026-04-15T14:30:00');
    expect(result).toMatch(/^\d{2} [A-Z]{3} \d{2}, \d{2}:\d{2}/);
  });
});
