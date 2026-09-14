// Independent oracle: the exact PackManifest options used by Cinc Registry.
package main

import (
	"context"
	"os"

	ocispec "github.com/opencontainers/image-spec/specs-go/v1"
	"oras.land/oras-go/v2"
	"oras.land/oras-go/v2/content"
	"oras.land/oras-go/v2/content/memory"
)

func main() {
	ctx := context.Background()
	payload, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	store := memory.New()
	layer := content.NewDescriptorFromBytes(ocispec.MediaTypeImageLayerGzip, payload)
	desc, err := oras.PackManifest(ctx, store, oras.PackManifestVersion1_1,
		"application/vnd.cinc.cookbook.v1+json", oras.PackManifestOptions{
			Layers:              []ocispec.Descriptor{layer},
			ManifestAnnotations: map[string]string{ocispec.AnnotationCreated: "1970-01-01T00:00:00Z"},
		})
	if err != nil {
		panic(err)
	}
	raw, err := content.FetchAll(ctx, store, desc)
	if err != nil {
		panic(err)
	}
	if _, err := os.Stdout.Write(raw); err != nil {
		panic(err)
	}
}
