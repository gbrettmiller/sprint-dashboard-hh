import { describe, it, expect } from 'vitest';
import { parseSection } from './parsing.js';

describe('parseSection', () => {
  const description = [
    '## User Story',
    'As a user, I want to see sprint metrics.',
    '',
    '## Acceptance Criteria',
    '- [ ] Dashboard loads',
    '- [ ] Chart renders',
    '',
    '## Description',
    'Some background context.',
  ].join('\n');

  it('extracts the content of a named section', () => {
    expect(parseSection(description, 'User Story')).toContain('As a user');
  });

  it('stops at the next header and does not bleed into the next section', () => {
    const result = parseSection(description, 'User Story');
    expect(result).not.toContain('Acceptance Criteria');
    expect(result).not.toContain('Dashboard loads');
  });

  it('returns null for a section that does not exist', () => {
    expect(parseSection(description, 'Implementation Notes')).toBeNull();
  });

  it('returns null for a null description', () => {
    expect(parseSection(null, 'User Story')).toBeNull();
  });

  it('is case-insensitive for the section name', () => {
    expect(parseSection(description, 'user story')).toContain('As a user');
    expect(parseSection(description, 'USER STORY')).toContain('As a user');
  });

  it('matches ## headers', () => {
    const h2 = '## User Story\nContent here.';
    expect(parseSection(h2, 'User Story')).toContain('Content here.');
  });

  it('matches ### headers', () => {
    const h3 = '### User Story\nContent here.';
    expect(parseSection(h3, 'User Story')).toContain('Content here.');
  });

  it('returns null for a section with no content', () => {
    expect(parseSection('## User Story\n\n## Next Section', 'User Story')).toBeNull();
  });

  it('returns the last section correctly (no following header)', () => {
    const result = parseSection(description, 'Description');
    expect(result).toContain('Some background context.');
  });
});
