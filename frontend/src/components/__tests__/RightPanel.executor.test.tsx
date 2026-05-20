import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RightPanel from '../RightPanel';

const okJson = (data: any) =>
  Promise.resolve({
    ok: true,
    json: async () => data,
    text: async () => '',
  } as Response);

const makeFetchMock = (overrides?: Record<string, any>) =>
  vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/context/status')) return okJson({ initialized: true, files: 1, symbols: 1, artifacts: 0, frameworks: [] });
    if (url.includes('/context/runtime')) return okJson({ artifacts: [], execution_chains: [], hot_symbols: [] });
    if (url.includes('/settings/prompts')) {
      return okJson(
        overrides?.promptSettings || {
          selected_preset_id: 'default',
          manual_file_add_enabled: false,
          allow_preset_change_in_preview: true,
          executor_response_format: 'nexus_edits_v2',
          presets: [
            {
              id: 'default',
              name: 'Nexus Default',
              description: 'Locked system template that ships with Nexus.',
              template: 'template',
              isDefault: true,
            },
          ],
        }
      );
    }
    if (url.includes('/settings/')) return okJson({});
    if (url.includes('/history/file')) return okJson({ status: 'success', entries: [] });
    if (url.includes('/history/project')) return okJson({ status: 'success', entries: [] });
    if (url.includes('/executor/patch/preview')) {
      return okJson(
        overrides?.preview || {
          status: 'success',
          preview: {
            files: [{ path: 'a.txt', hunk_count: 1 }],
            stats: { additions: 1, deletions: 0 },
            can_apply: true,
            warnings: [],
            blockers: [],
            issues: [],
            intent_checks: { required_contains: [], required_absent: [] },
          },
        }
      );
    }
    if (url.includes('/executor/patch/apply')) {
      return okJson(
        overrides?.apply || {
          status: 'success',
          apply: {
            files: [{ path: 'a.txt', hunk_count: 1 }],
            stats: { additions: 1, deletions: 0 },
            can_apply: true,
            warnings: [],
            blockers: [],
            issues: [],
            results: [{ path: 'a.txt', status: 'updated' }],
            snapshot_id: 'abc',
            snapshot_created: true,
          },
        }
      );
    }
    if (url.includes('/executor/patch/autofetch')) return okJson({ status: 'success', autofetch: overrides?.autofetch || { detected_format: 'nexus_edits_v2', normalized_text: '{"format":"nexus_edits_v2","edits":[]}', issues: [] } });
    return okJson({});
  });

describe('Executor modal', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', makeFetchMock());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('opens Executor popup from button', async () => {
    render(
      <RightPanel
        activeTab={{ path: 'a.txt', content: 'x', savedContent: 'x', isDirty: false }}
        isProjectLoaded={true}
        workspaceFiles={[]}
        dirtyPaths={new Set()}
      />
    );

    await waitFor(() => expect(screen.getByText('Execution Engine')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Executor'));
    await waitFor(() => expect(screen.getByText('Patch')).toBeInTheDocument());
  });

  it('auto-fetches uncertain output into executable payload', async () => {
    vi.stubGlobal(
      'fetch',
      makeFetchMock({
        promptSettings: {
          selected_preset_id: 'default',
          manual_file_add_enabled: false,
          allow_preset_change_in_preview: true,
          executor_response_format: 'nexus_edits_v2',
          presets: [{ id: 'default', name: 'Nexus Default', description: 'd', template: 't', isDefault: true }],
        },
        autofetch: {
          detected_format: 'nexus_edits_v2',
          normalized_text: '{"format":"nexus_edits_v2","edits":[]}',
          issues: [],
        },
      })
    );

    render(
      <RightPanel
        activeTab={{ path: 'a.txt', content: 'x', savedContent: 'x', isDirty: false }}
        isProjectLoaded={true}
        workspaceFiles={[]}
        dirtyPaths={new Set()}
      />
    );

    await waitFor(() => expect(screen.getByText('Execution Engine')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Executor'));
    await waitFor(() => expect(screen.getByText('Patch')).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText('Paste full uncertain AI output (with prose/markdown).'), { target: { value: 'messy ai output' } });
    fireEvent.click(screen.getByText('Auto Fetch Payload'));
    await waitFor(() => expect(screen.getByDisplayValue('{"format":"nexus_edits_v2","edits":[]}')).toBeInTheDocument());
  });

  it('disables apply when preview returns blockers and shows why blocked', async () => {
    vi.stubGlobal(
      'fetch',
      makeFetchMock({
        preview: {
          status: 'success',
          preview: {
            files: [{ path: 'calculator.py', hunk_count: 1 }],
            stats: { additions: 2, deletions: 1 },
            can_apply: false,
            warnings: [{ reason: 'repaired_unescaped_quotes' }],
            blockers: [{ reason: 'intent_mismatch', details: 'missing required token: ^2' }],
            issues: [
              { reason: 'repaired_unescaped_quotes' },
              { reason: 'intent_mismatch', details: 'missing required token: ^2' },
            ],
            blocked_stage: 'intent_guard',
            intent_checks: { required_contains: ['^2'], required_absent: [] },
          },
        },
      })
    );

    render(
      <RightPanel
        activeTab={{ path: 'calculator.py', content: 'x', savedContent: 'x', isDirty: false }}
        isProjectLoaded={true}
        workspaceFiles={[]}
        dirtyPaths={new Set()}
      />
    );

    await waitFor(() => expect(screen.getByText('Execution Engine')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Executor'));
    await waitFor(() => expect(screen.getByText('Patch')).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText('Paste nexus_edits_v2 JSON payload'), { target: { value: '{"format":"nexus_edits_v2","edits":[]}' } });
    fireEvent.click(screen.getByText('Open Preview Bubble'));
    fireEvent.click(screen.getByText('Preview Patch'));
    fireEvent.click(screen.getByText('Show Details'));

    await waitFor(() => expect(screen.getByText(/Patch blocked at intent_guard/)).toBeInTheDocument());
    expect(screen.getByText('Warnings')).toBeInTheDocument();
    expect(screen.getByText('repaired_unescaped_quotes')).toBeInTheDocument();
    expect(screen.getByText('Blockers')).toBeInTheDocument();
    expect(screen.getByText('intent_mismatch')).toBeInTheDocument();
    expect(screen.getByText('Apply')).toBeDisabled();
  });

  it('shows verify failure and rollback result when apply fails post-verify', async () => {
    vi.stubGlobal(
      'fetch',
      makeFetchMock({
        preview: {
          status: 'success',
          preview: {
            files: [{ path: 'a.txt', hunk_count: 1 }],
            stats: { additions: 1, deletions: 0 },
            can_apply: true,
            warnings: [],
            blockers: [],
            issues: [],
            intent_checks: { required_contains: [], required_absent: [] },
          },
        },
        apply: {
          status: 'success',
          apply: {
            files: [{ path: 'a.txt', hunk_count: 1 }],
            stats: { additions: 1, deletions: 0 },
            can_apply: false,
            blocked_stage: 'verify',
            warnings: [],
            blockers: [{ reason: 'verify_failed', details: 'forced' }],
            issues: [{ reason: 'verify_failed', details: 'forced' }],
            results: [{ path: 'a.txt', status: 'updated' }],
            verification_passed: false,
            rollback: { attempted: true, success: true },
          },
        },
      })
    );

    render(
      <RightPanel
        activeTab={{ path: 'a.txt', content: 'x', savedContent: 'x', isDirty: false }}
        isProjectLoaded={true}
        workspaceFiles={[]}
        dirtyPaths={new Set()}
      />
    );

    await waitFor(() => expect(screen.getByText('Execution Engine')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Executor'));
    await waitFor(() => expect(screen.getByText('Patch')).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText('Paste nexus_edits_v2 JSON payload'), { target: { value: '{"format":"nexus_edits_v2","edits":[]}' } });
    fireEvent.click(screen.getByText('Open Preview Bubble'));
    fireEvent.click(screen.getByText('Preview Patch'));
    await waitFor(() => expect(screen.getByText('Patch preview ready.')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Apply'));
    await waitFor(() => expect(screen.getAllByText(/Verification failed after apply/).length).toBeGreaterThan(0));
  });

  it('keeps draft payload across tab switches', async () => {
    render(
      <RightPanel
        activeTab={{ path: 'a.txt', content: 'x', savedContent: 'x', isDirty: false }}
        isProjectLoaded={true}
        workspaceFiles={[]}
        dirtyPaths={new Set()}
      />
    );

    await waitFor(() => expect(screen.getByText('Execution Engine')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Executor'));
    await waitFor(() => expect(screen.getByText('Patch')).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText('Paste nexus_edits_v2 JSON payload'), { target: { value: '{"format":"nexus_edits_v2","edits":[{"path":"a.txt","op":"delete_file"}]}' } });
    fireEvent.click(screen.getByText('Recover'));
    fireEvent.click(screen.getByText('Patch'));
    expect(screen.getByDisplayValue('{"format":"nexus_edits_v2","edits":[{"path":"a.txt","op":"delete_file"}]}')).toBeInTheDocument();
  });
});
