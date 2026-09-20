import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { ReicheltImportForm } from './ImportForm';

// This is the function which is called by InvenTree to render the actual dashboard component
export function RenderReicheltAutoImportDashboardItem(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return <ReicheltImportForm context={context} />;
}
