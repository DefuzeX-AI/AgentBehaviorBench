#include "SCameraView.h"

#include "ue5project/Interaction/UserInterface/Equipment/EquipmentWidgetStyleSet.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Images/SImage.h"

void SCameraView::Construct(const FArguments& InArgs)
{
	RenderTarget = InArgs._RenderTarget;
	SlateBrush = new FSlateImageBrush(RenderTarget.Get(), FVector2D(400.0, 300.0));
	
	const FSlateBrush* BackgroundImageBrush = FEquipmentWidgetStyleSet::Get()->GetBrush(TEXT("BackgroundImageBrush"));

	ChildSlot
	[
		SNew(SBox)
		.WidthOverride(414.f)
		.HeightOverride(314.f)
		[
			SNew(SOverlay)
			+ SOverlay::Slot()
			[
				SNew(SImage)
				.Image(BackgroundImageBrush)
			]
			+ SOverlay::Slot()
			.HAlign(HAlign_Center)
			.VAlign(VAlign_Center)
			[
				SNew(SImage)
				.Image(SlateBrush)
			]
		]
	];
}

