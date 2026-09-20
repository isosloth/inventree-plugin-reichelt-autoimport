import type { InvenTreePluginContext } from '@inventreedb/ui';

import { ReicheltImportForm } from './ImportForm';

export function RenderPluginSettings(context: InvenTreePluginContext) {
  return <ReicheltImportForm context={context} />;
}
