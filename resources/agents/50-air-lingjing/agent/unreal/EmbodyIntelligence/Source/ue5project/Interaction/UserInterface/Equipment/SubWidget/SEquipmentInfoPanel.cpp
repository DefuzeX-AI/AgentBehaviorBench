#include "SEquipmentInfoPanel.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SSeparator.h"

void SEquipmentInfoPanel::Construct(const FArguments& InArgs)
{
	const FEquipmentInfo EquipmentInfo = InArgs._EquipmentInfo;
	switch (EquipmentInfo.Type)
	{
	case EEquipmentType::Drone: EquipmentTypeStr = TEXT("\u65e0\u4eba\u673a"); break;
	case EEquipmentType::Car: EquipmentTypeStr = TEXT("\u65e0\u4eba\u8f66"); break;
	case EEquipmentType::Dog: EquipmentTypeStr = TEXT("\u65e0\u4eba\u72d7"); break;
	case EEquipmentType::Ship: EquipmentTypeStr = TEXT("\u8239\u8236"); break;
	default: EquipmentTypeStr = TEXT("\u672a\u77e5"); break;
	}
	EquipmentId = EquipmentInfo.EquipmentId;
	EquipmentName = EquipmentInfo.EquipmentName;
	
	ChildSlot
	[
		SNew(SBorder)
		.BorderImage(FCoreStyle::Get().GetBrush("ToolPanel.GroupBorder"))
		.Padding(8.0f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(STextBlock)
				.Text(FText::FromString(TEXT("\u88c5\u5907\u4fe1\u606f")))
				.Font(FCoreStyle::GetDefaultFontStyle("Bold", 12))
				.ColorAndOpacity(FLinearColor::White)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0, 4, 0, 0))
			[
				SNew(SSeparator)
				.Orientation(Orient_Horizontal)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0, 4, 0, 0))
			[
				SNew(STextBlock)
				.Font(FCoreStyle::GetDefaultFontStyle("Regular", 10))
				.ColorAndOpacity(FLinearColor(FColor(200, 220, 255)))
			]
			+ SVerticalBox::Slot()
			.FillHeight(1.0f)
			.Padding(FMargin(0, 4, 0, 0))
			[
				SNew(SScrollBox)
				+ SScrollBox::Slot()
				[
					SNew(STextBlock)
					.Font(FCoreStyle::GetDefaultFontStyle("Regular", 9))
					.ColorAndOpacity(FLinearColor(FColor(180, 200, 180)))
					.AutoWrapText(true)
				]
			]
		]
	];
}

void SEquipmentInfoPanel::UpdateTransform(const FTransform& InTransform)
{
	Location = InTransform.GetTranslation();
	Rotation = InTransform.GetRotation().Rotator();
	Scale = InTransform.GetScale3D();
}

