import { allCountries } from 'country-region-data';
import type { CountryData, Region } from 'country-region-data';
import type { SelectOption } from '../ui/Primitives';

const locationSorter = new Intl.Collator(undefined, { sensitivity: 'base' });

const countries = (allCountries as CountryData[])
  .filter(([name]) => Boolean(name))
  .sort(([leftName], [rightName]) => locationSorter.compare(leftName, rightName));

const countryByName = new Map<string, CountryData>(countries.map((country) => [country[0], country]));

export function getCountryOptions(): SelectOption[] {
  return countries.map(([name]) => ({
    value: name,
    label: name,
    description: 'Country',
  }));
}

export function getStateOptions(countryName: string): SelectOption[] {
  const country = countryByName.get(countryName.trim());
  if (!country) return [];

  const [name, , regions] = country;
  return regions
    .filter((region: Region) => Boolean(region[0]))
    .sort(([leftName], [rightName]) => locationSorter.compare(leftName, rightName))
    .map(([regionName]) => ({
      value: regionName,
      label: regionName,
      description: `${name} state/region`,
    }));
}
