import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Button,
  Group,
  List,
  NumberInput,
  Stack,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';

interface ImportResult {
  result: 'created' | 'updated';
  sku: string;
  part: number;
  part_name: string;
  supplier_part: number;
  unit_price: string | null;
  price_breaks: { quantity: string; price: string }[];
  stock_item: number | null;
}

export function ReicheltImportForm({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [code, setCode] = useState('');
  const [quantity, setQuantity] = useState<number | ''>(1);
  const [loading, setLoading] = useState(false);
  const [lastResult, setLastResult] = useState<ImportResult | null>(null);

  const importPart = async () => {
    if (!code.trim()) {
      notifications.show({
        title: 'Reichelt product URL required',
        message: 'Enter the "code" (Reichelt product page URL) to import',
        color: 'red'
      });
      return;
    }

    setLoading(true);
    try {
      const response = await context.api.post(
        '/plugin/reichelt-auto-import/import/',
        { code, quantity: quantity === '' ? 1 : quantity }
      );
      const data = response.data as ImportResult;
      setLastResult(data);
      notifications.show({
        title: data.result === 'created' ? 'Part created' : 'Part updated',
        message: `${data.part_name} (${data.sku})`,
        color: 'green'
      });
    } catch (error: any) {
      notifications.show({
        title: 'Import failed',
        message:
          error?.response?.data?.error ?? error?.message ?? 'Unknown error',
        color: 'red'
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Stack gap='sm'>
      <Title order={4}>Import a Reichelt Part</Title>
      <Text size='sm' c='dimmed'>
        Paste the Reichelt product page URL or Manufacturer part number here.
      </Text>
      <TextInput
        label='Code (Reichelt product URL)'
        placeholder='https://www.reichelt.com/de/en/shop/product/...'
        value={code}
        onChange={(event) => setCode(event.currentTarget.value)}
      />
      <NumberInput
        label='Quantity'
        min={1}
        value={quantity}
        onChange={(value) => setQuantity(value as number | '')}
      />
      <Group>
        <Button onClick={importPart} loading={loading}>
          Import
        </Button>
        {lastResult && (
          <Button
            component='a'
            href={`/web/part/${lastResult.part}`}
            target='_blank'
          >
            View last imported Part
          </Button>
        )}
      </Group>

      {lastResult && (
        <Alert
          color='blue'
          title={`Part ${lastResult.part} ${lastResult.result}`}
        >
          <Text>
            {lastResult.part_name} ({lastResult.sku})
          </Text>
          {lastResult.unit_price && (
            <Text size='sm'>Unit price (qty 1): {lastResult.unit_price}</Text>
          )}
          {lastResult.price_breaks.length > 0 && (
            <List size='sm'>
              {lastResult.price_breaks.map((priceBreak) => (
                <List.Item key={priceBreak.quantity}>
                  {priceBreak.quantity}x: {priceBreak.price}
                </List.Item>
              ))}
            </List>
          )}
        </Alert>
      )}
    </Stack>
  );
}
