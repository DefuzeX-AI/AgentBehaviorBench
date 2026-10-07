// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

class FDefaultStyleSet final
{
	FDefaultStyleSet()
	{}
	~FDefaultStyleSet()
	{}

public:
	/* ButtonStyleSet */
	static FButtonStyle* GetNoDrawTypeButtonStyle()
	{
		FButtonStyle* ButtonStyle = new FButtonStyle();
		ButtonStyle->Normal.DrawAs = ESlateBrushDrawType::NoDrawType;
		ButtonStyle->Hovered.DrawAs = ESlateBrushDrawType::NoDrawType;
		ButtonStyle->Pressed.DrawAs = ESlateBrushDrawType::NoDrawType;
		ButtonStyle->NormalPadding = FMargin();
		ButtonStyle->PressedPadding = FMargin();

		return ButtonStyle;
	}


	/* FontStyleSet */
//	static FSlateFontInfo GetSourceHanSanSSCFontStyle(const int32 InSize, const FName InTypefaceFontName)
//	{
//		const FString SourceHanSanSSCFontPath = TEXT("/Script/Engine.Font'/Game/Program/UserInterface/Font/HanSanSSC/SourceHanSanSSC.SourceHanSanSSC'");
//		UObject* Asset = LoadObject<UObject>(nullptr, *SourceHanSanSSCFontPath);
//		if (Asset)
//		{
//			Asset->AddToRoot();
//		}
//		return FSlateFontInfo(Asset, InSize, InTypefaceFontName);
//	}
	
};

