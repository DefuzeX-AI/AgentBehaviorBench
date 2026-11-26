// Build-time helper: list every built-in provider id of the locked omp catalog
// whose startup model discovery could reach the network (bundled catalog
// providers, models.dev catalog-overlay providers and endpoint-discovery
// providers). bootstrap/launch.py disables all of them so only the configured
// GLM provider remains. Reads the installed package; makes no network calls.
import { getBundledProviders } from "@oh-my-pi/pi-catalog/models";
import { MODELS_DEV_CATALOG_PROVIDER_IDS, PROVIDER_DESCRIPTORS } from "@oh-my-pi/pi-catalog/provider-models";

const ids = new Set<string>([
	...getBundledProviders(),
	...MODELS_DEV_CATALOG_PROVIDER_IDS,
	...PROVIDER_DESCRIPTORS.map(descriptor => descriptor.providerId),
]);
console.log(JSON.stringify([...ids].sort()));
