#include "SEquipmentMiniMap.h"

#include "Rendering/DrawElements.h"
#include "ue5project/Interaction/UserInterface/Equipment/EquipmentWidgetStyleSet.h"

void SEquipmentMiniMap::Construct(const FArguments& InArgs)
{
	const FSlateBrush* BackgroundImageBrush = FEquipmentWidgetStyleSet::Get()->GetBrush(TEXT("BackgroundImageBrush"));
	const FSlateBrush* MapImageBrush = FEquipmentWidgetStyleSet::Get()->GetBrush(TEXT("MapImageBrush"));
	
	ChildSlot
	[
		SNew(SBox)
		.WidthOverride(414.f)
		.HeightOverride(414.f)
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
				SNew(SBox)
				.WidthOverride(400.f)
				.HeightOverride(400.f)
				[
					SNew(SImage)
					.Image(MapImageBrush)
				]
			]
		]
	];
}

void SEquipmentMiniMap::AddTrajectoryPoint(const FVector2D& InPoint)
{
	TrajectoryPoints.Add(InPoint);
}

void SEquipmentMiniMap::ClearTrajectory()
{
	TrajectoryPoints.Empty();
}


