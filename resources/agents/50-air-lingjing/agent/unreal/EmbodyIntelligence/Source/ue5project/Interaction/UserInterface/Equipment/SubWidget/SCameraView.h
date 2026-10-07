#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Engine/TextureRenderTarget2D.h"

class SCameraView : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SCameraView) {}
	SLATE_ARGUMENT(TWeakObjectPtr<UTextureRenderTarget2D>, RenderTarget)	
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	TWeakObjectPtr<UTextureRenderTarget2D> RenderTarget;
	FSlateBrush* SlateBrush = nullptr;

};
